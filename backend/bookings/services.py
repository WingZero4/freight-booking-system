"""
Service layer for the freight booking system.

ALL booking mutations (create, edit, submit, cancel, etc.) go through
BookingService. This ensures:
  1. Consistent validation via validators.py
  2. Automatic audit logging
  3. Single entry point for web, API, EDI, and CSV channels

Views and serializers should NEVER mutate Booking/BookingItem directly.
"""
import threading

from django.db import transaction
from django.utils import timezone

from .models import (
    Booking, BookingItem, BookingDocument, BookingParty, Party, AuditLog,
)
from . import notifications, validators

import logging

logger = logging.getLogger(__name__)


def _safe_fms_dispatch(func, *args, **kwargs):
    """Call an FMS dispatch function in a background thread.

    FMS integration is fire-and-forget — failures must never
    block booking status transitions. The dispatch runs in a
    daemon thread so the HTTP response returns immediately.
    The background worker recovers any dispatches that fail
    due to thread/process termination.
    """
    def _run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            from integrations import dispatch as fms_dispatch
            getattr(fms_dispatch, func)(*args, **kwargs)
        except Exception:
            booking = args[0] if args else None
            booking_num = getattr(booking, 'booking_number', '?')
            logger.exception('FMS dispatch (%s) failed for %s', func, booking_num)
        finally:
            close_old_connections()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _safe_carrier_dispatch(func, *args, **kwargs):
    """Call a carrier dispatch function in a background thread.

    Carrier integration is fire-and-forget — failures must never
    block booking status transitions.
    """
    def _run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            from integrations import carrier_dispatch
            getattr(carrier_dispatch, func)(*args, **kwargs)
        except Exception:
            booking = args[0] if args else None
            booking_num = getattr(booking, 'booking_number', '?')
            logger.exception('Carrier dispatch (%s) failed for %s', func, booking_num)
        finally:
            close_old_connections()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _should_defer_fms_push(booking):
    """Check if FMS push should be deferred until carrier confirms.

    Returns True if booking has a carrier config with auto_chain_to_fms
    enabled, meaning FMS push will be triggered after carrier confirmation.
    """
    if not booking.carrier_config_id:
        return False
    try:
        from integrations.models import CarrierConfig
        cc = CarrierConfig.objects.get(pk=booking.carrier_config_id, is_active=True)
        return cc.auto_chain_to_fms
    except Exception:
        return False


class BookingService:
    """Centralised service for all booking operations."""

    # ─── Audit helpers ────────────────────────────────────────────────

    @staticmethod
    def _log(booking, action, user=None, old_value=None, new_value=None,
             notes='', request=None):
        """Write an audit log entry."""
        ip = None
        ua = ''
        if request:
            # Use REMOTE_ADDR as primary (set correctly by reverse proxy)
            # Only fall back to XFF rightmost IP if REMOTE_ADDR is missing
            ip = request.META.get('REMOTE_ADDR', '')
            if not ip:
                xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
                if xff:
                    ip = xff.split(',')[-1].strip()
            ua = request.META.get('HTTP_USER_AGENT', '')[:500]

        AuditLog.objects.create(
            booking=booking,
            action=action,
            performed_by=user,
            performed_at=timezone.now(),
            old_value=old_value,
            new_value=new_value,
            ip_address=ip or None,
            user_agent=ua,
            notes=notes,
        )

    @staticmethod
    def _booking_snapshot(booking):
        """Return a JSON-safe dict of key booking fields for audit diffs."""
        return {
            'status': booking.status,
            'transport_mode': booking.transport_mode,
            'origin_port': booking.origin_port_id,
            'destination_port': booking.destination_port_id,
            'cargo_ready_date': str(booking.cargo_ready_date),
            'container_type': booking.container_type_id,
            'container_count': booking.container_count,
            'incoterms': booking.incoterms,
            'incoterms_location': booking.incoterms_location,
            'commodity_description': booking.commodity_description,
            'is_hazardous': booking.is_hazardous,
            'special_instructions': booking.special_instructions,
            'external_reference': booking.external_reference,
            'chargeable_weight_kg': str(booking.chargeable_weight_kg) if booking.chargeable_weight_kg else None,
            'flight_number': booking.flight_number,
        }

    # ─── Create ───────────────────────────────────────────────────────

    @classmethod
    def create_booking(cls, form, formset, customer, user, request=None,
                       source_channel='WEB'):
        """
        Create a booking from validated Django form + formset.

        Returns the new Booking instance.
        Raises ValueError if form/formset are invalid.
        """
        if not form.is_valid() or not formset.is_valid():
            raise ValueError('Invalid form data.')

        with transaction.atomic():
            booking = form.save(commit=False)
            booking.customer = customer
            booking.created_by = user
            booking.source_channel = source_channel
            booking.save()

            formset.instance = booking
            formset.save()

            booking.recalculate_totals()

            cls._log(
                booking, 'CREATED', user=user, request=request,
                new_value=cls._booking_snapshot(booking),
            )

        return booking

    # ─── Update ───────────────────────────────────────────────────────

    @classmethod
    def update_booking(cls, booking, form, formset, user, request=None):
        """
        Update an existing DRAFT booking from validated form + formset.

        Returns the updated Booking instance.
        Raises ValueError if booking is not DRAFT or forms are invalid.
        """
        if booking.status != 'DRAFT':
            raise ValueError('Only draft bookings can be edited.')

        if not form.is_valid() or not formset.is_valid():
            raise ValueError('Invalid form data.')

        old = cls._booking_snapshot(booking)

        with transaction.atomic():
            form.save()
            formset.save()
            booking.refresh_from_db()
            booking.recalculate_totals()

            cls._log(
                booking, 'UPDATED', user=user, request=request,
                old_value=old,
                new_value=cls._booking_snapshot(booking),
            )

        return booking

    # ─── Dict-based create/update (API and EDI channels) ────────────

    @classmethod
    def create_booking_from_data(cls, data, items_data, customer, user,
                                  request=None, source_channel='API',
                                  parties_data=None):
        """
        Create a booking from validated data dicts (API/EDI channels).

        Args:
            data: dict with Booking model fields. Port/ContainerType
                  should be model instances (not PKs).
            items_data: list of dicts matching BookingItem fields.
            customer: Customer instance.
            user: User performing the action.
            request: Optional HttpRequest for audit logging.
            source_channel: 'API', 'EDI', etc.
            parties_data: Optional list of dicts for BookingParty.

        Returns the new Booking instance.
        """
        with transaction.atomic():
            booking = Booking(
                customer=customer,
                created_by=user,
                source_channel=source_channel,
                transport_mode=data['transport_mode'],
                origin_port=data['origin_port'],
                destination_port=data['destination_port'],
                cargo_ready_date=data['cargo_ready_date'],
                container_type=data.get('container_type'),
                container_count=data.get('container_count'),
                incoterms=data.get('incoterms', 'FOB'),
                incoterms_location=data.get('incoterms_location', ''),
                commodity_description=data.get('commodity_description', ''),
                is_hazardous=data.get('is_hazardous', False),
                external_reference=data.get('external_reference', ''),
                special_instructions=data.get('special_instructions', ''),
                chargeable_weight_kg=data.get('chargeable_weight_kg'),
                flight_number=data.get('flight_number', ''),
            )
            booking.save()

            for item_data in items_data:
                BookingItem.objects.create(
                    booking=booking,
                    description=item_data['description'],
                    package_type=item_data.get('package_type', 'PACKAGE'),
                    quantity=item_data['quantity'],
                    weight_kg=item_data['weight_kg'],
                    hs_code=item_data.get('hs_code', ''),
                    volume_cbm=item_data.get('volume_cbm'),
                    length_cm=item_data.get('length_cm'),
                    width_cm=item_data.get('width_cm'),
                    height_cm=item_data.get('height_cm'),
                    marks_and_numbers=item_data.get('marks_and_numbers', ''),
                    is_hazardous=item_data.get('is_hazardous', False),
                    un_number=item_data.get('un_number', ''),
                    imo_class=item_data.get('imo_class', ''),
                    country_of_origin=item_data.get('country_of_origin', ''),
                )

            if parties_data:
                for party_data in parties_data:
                    BookingParty.objects.create(
                        booking=booking,
                        role=party_data['role'],
                        company_name=party_data['company_name'],
                        contact_name=party_data.get('contact_name', ''),
                        address_text=party_data.get('address_text', ''),
                        email=party_data.get('email', ''),
                        phone=party_data.get('phone', ''),
                        tax_id=party_data.get('tax_id', ''),
                    )

            booking.recalculate_totals()

            cls._log(
                booking, 'CREATED', user=user, request=request,
                new_value=cls._booking_snapshot(booking),
                notes=f'Created via {source_channel}',
            )

        return booking

    @classmethod
    def update_booking_from_data(cls, booking, data, user, request=None,
                                  items_data=None):
        """
        Update a DRAFT booking from validated data dicts.

        Args:
            booking: Existing Booking instance (must be DRAFT).
            data: dict of fields to update. Only provided keys are changed.
            user: User performing the action.
            request: Optional HttpRequest for audit logging.
            items_data: If provided, replaces all existing items.

        Returns the updated Booking instance.
        Raises ValueError if booking is not DRAFT.
        """
        if booking.status != 'DRAFT':
            raise ValueError('Only draft bookings can be edited.')

        old = cls._booking_snapshot(booking)

        with transaction.atomic():
            updatable_fields = [
                'transport_mode', 'origin_port', 'destination_port',
                'cargo_ready_date', 'container_type', 'container_count',
                'incoterms', 'incoterms_location', 'commodity_description',
                'is_hazardous', 'external_reference', 'special_instructions',
                'chargeable_weight_kg', 'flight_number',
            ]
            for field in updatable_fields:
                if field in data:
                    setattr(booking, field, data[field])

            booking.save()

            if items_data is not None:
                booking.items.all().delete()
                for item_data in items_data:
                    BookingItem.objects.create(
                        booking=booking,
                        description=item_data['description'],
                        package_type=item_data.get('package_type', 'PACKAGE'),
                        quantity=item_data['quantity'],
                        weight_kg=item_data['weight_kg'],
                        hs_code=item_data.get('hs_code', ''),
                        volume_cbm=item_data.get('volume_cbm'),
                        length_cm=item_data.get('length_cm'),
                        width_cm=item_data.get('width_cm'),
                        height_cm=item_data.get('height_cm'),
                        marks_and_numbers=item_data.get('marks_and_numbers', ''),
                        is_hazardous=item_data.get('is_hazardous', False),
                        un_number=item_data.get('un_number', ''),
                        imo_class=item_data.get('imo_class', ''),
                        country_of_origin=item_data.get('country_of_origin', ''),
                    )

            booking.recalculate_totals()

            cls._log(
                booking, 'UPDATED', user=user, request=request,
                old_value=old,
                new_value=cls._booking_snapshot(booking),
            )

        return booking

    # ─── Status transitions ───────────────────────────────────────────

    @classmethod
    def submit_booking(cls, booking, user, request=None):
        """Submit a DRAFT booking. Raises ValueError on failure."""
        if booking.status != 'DRAFT':
            raise ValueError('Only draft bookings can be submitted.')
        if not booking.items.exists():
            raise ValueError('Cannot submit a booking with no cargo items.')
        if booking.transport_mode == 'SEA_FCL':
            if not booking.container_type or not booking.container_count:
                raise ValueError('FCL bookings require container type and count before submission.')

        with transaction.atomic():
            booking.recalculate_totals()
            booking.status = 'SUBMITTED'
            booking.submitted_at = timezone.now()
            booking.save()

            cls._log(booking, 'SUBMITTED', user=user, request=request)

        notifications.notify_booking_submitted(booking)

    @classmethod
    def confirm_booking(cls, booking, user=None, request=None):
        """Confirm a SUBMITTED booking (operations action)."""
        if booking.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be confirmed.')

        with transaction.atomic():
            booking.status = 'CONFIRMED'
            booking.confirmed_at = timezone.now()
            booking.confirmed_by = user
            booking.save()

            cls._log(booking, 'CONFIRMED', user=user, request=request)

        notifications.notify_booking_confirmed(booking)

        # If carrier config assigned, send to carrier
        if booking.carrier_config_id:
            _safe_carrier_dispatch('dispatch_carrier_booking', booking)

        # Push to customer FMS (unless deferred to after carrier confirms)
        if not _should_defer_fms_push(booking):
            _safe_fms_dispatch('dispatch_booking_confirmed', booking)

    @classmethod
    def reject_booking(cls, booking, user=None, reason='', request=None):
        """Reject a SUBMITTED booking."""
        if booking.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be rejected.')

        with transaction.atomic():
            booking.status = 'REJECTED'
            booking.rejected_at = timezone.now()
            booking.rejected_by = user
            booking.rejection_reason = reason
            booking.save()

            cls._log(
                booking, 'REJECTED', user=user, request=request,
                notes=reason,
            )

        notifications.notify_booking_rejected(booking)

    @classmethod
    def mark_in_transit(cls, booking, user=None, request=None,
                        actual_departure_date=None):
        """Mark a CONFIRMED booking as in transit."""
        if booking.status != 'CONFIRMED':
            raise ValueError('Only confirmed bookings can be marked in transit.')

        with transaction.atomic():
            booking.status = 'IN_TRANSIT'
            booking.in_transit_at = timezone.now()
            if actual_departure_date:
                booking.actual_departure_date = actual_departure_date
            booking.save()

            cls._log(booking, 'IN_TRANSIT', user=user, request=request)

        notifications.notify_booking_in_transit(booking)
        _safe_fms_dispatch('dispatch_milestone_update', booking, 'IN_TRANSIT')

    @classmethod
    def complete_booking(cls, booking, user=None, request=None,
                         actual_arrival_date=None):
        """Mark an IN_TRANSIT booking as completed."""
        if booking.status != 'IN_TRANSIT':
            raise ValueError('Only in-transit bookings can be completed.')

        with transaction.atomic():
            booking.status = 'COMPLETED'
            booking.completed_at = timezone.now()
            if actual_arrival_date:
                booking.actual_arrival_date = actual_arrival_date
            booking.save()

            cls._log(booking, 'COMPLETED', user=user, request=request)

        notifications.notify_booking_completed(booking)
        _safe_fms_dispatch('dispatch_milestone_update', booking, 'COMPLETED')

    @classmethod
    def confirm_booking_with_carrier(cls, booking, carrier_form, user=None, request=None):
        """Confirm a SUBMITTED booking and save carrier details in one transaction."""
        if booking.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be confirmed.')

        if carrier_form and not carrier_form.is_valid():
            raise ValueError('Invalid carrier details.')

        with transaction.atomic():
            if carrier_form and carrier_form.cleaned_data:
                for field in carrier_form.cleaned_data:
                    setattr(booking, field, carrier_form.cleaned_data[field])

            # Auto-populate carrier_name from selected config if blank
            if booking.carrier_config_id and not booking.carrier_name:
                booking.carrier_name = booking.carrier_config.carrier_name

            booking.status = 'CONFIRMED'
            booking.confirmed_at = timezone.now()
            booking.confirmed_by = user
            booking.save()

            cls._log(booking, 'CONFIRMED', user=user, request=request)

        notifications.notify_booking_confirmed(booking)

        # If carrier config assigned, send to carrier
        if booking.carrier_config_id:
            _safe_carrier_dispatch('dispatch_carrier_booking', booking)

        # Push to customer FMS (unless deferred to after carrier confirms)
        if not _should_defer_fms_push(booking):
            _safe_fms_dispatch('dispatch_booking_confirmed', booking)
        return booking

    @classmethod
    def update_carrier_details(cls, booking, form, user=None, request=None):
        """Update carrier details on a CONFIRMED or IN_TRANSIT booking."""
        if booking.status not in ('CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Carrier details can only be updated on confirmed or in-transit bookings.')

        if not form.is_valid():
            raise ValueError('Invalid carrier details.')

        old = {
            'carrier_config_id': booking.carrier_config_id,
            'carrier_name': booking.carrier_name,
            'vessel_name': booking.vessel_name,
            'voyage_number': booking.voyage_number,
            'cargo_cutoff_date': str(booking.cargo_cutoff_date) if booking.cargo_cutoff_date else None,
            'etd': str(booking.etd) if booking.etd else None,
            'eta': str(booking.eta) if booking.eta else None,
            'carrier_booking_ref': booking.carrier_booking_ref,
            'contract_number': booking.contract_number,
        }

        with transaction.atomic():
            form.save()
            booking.refresh_from_db()

            new = {
                'carrier_config_id': booking.carrier_config_id,
                'carrier_name': booking.carrier_name,
                'vessel_name': booking.vessel_name,
                'voyage_number': booking.voyage_number,
                'cargo_cutoff_date': str(booking.cargo_cutoff_date) if booking.cargo_cutoff_date else None,
                'etd': str(booking.etd) if booking.etd else None,
                'eta': str(booking.eta) if booking.eta else None,
                'carrier_booking_ref': booking.carrier_booking_ref,
                'contract_number': booking.contract_number,
            }

            cls._log(
                booking, 'UPDATED', user=user, request=request,
                old_value=old, new_value=new,
                notes='Carrier details updated',
            )

        return booking

    # ─── Carrier integration ─────────────────────────────────────────

    @classmethod
    def assign_carrier_config(cls, booking, carrier_config, user=None, request=None):
        """Assign a carrier config to a booking (operations action)."""
        if booking.status not in ('SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Carrier can only be assigned to active bookings.')

        old_config_id = booking.carrier_config_id

        with transaction.atomic():
            booking.carrier_config = carrier_config
            if not booking.carrier_name:
                booking.carrier_name = carrier_config.carrier_name
            booking.save(update_fields=[
                'carrier_config', 'carrier_name', 'updated_at',
            ])

            cls._log(
                booking, 'UPDATED', user=user, request=request,
                old_value={'carrier_config_id': old_config_id},
                new_value={
                    'carrier_config_id': carrier_config.pk,
                    'carrier_name': carrier_config.carrier_name,
                },
                notes='Carrier config assigned',
            )

        return booking

    @classmethod
    def submit_to_carrier(cls, booking, user=None, request=None):
        """Explicitly submit a booking to its assigned carrier API.

        Used when ops wants to trigger carrier submission separately from confirm.
        """
        if not booking.carrier_config_id:
            raise ValueError('No carrier config assigned to this booking.')
        if booking.status not in ('CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Booking must be confirmed before submitting to carrier.')
        if booking.carrier_request_status in ('SUBMITTED', 'CONFIRMED'):
            raise ValueError('Booking has already been submitted to the carrier.')

        cls._log(
            booking, 'UPDATED', user=user, request=request,
            notes='Manual carrier submission triggered',
        )

        _safe_carrier_dispatch('dispatch_carrier_booking', booking)

    @classmethod
    def cancel_booking(cls, booking, user=None, reason='', request=None):
        """Cancel a DRAFT, SUBMITTED, or CONFIRMED booking.

        Cancelling a CONFIRMED booking requires a reason and is staff-only.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED'):
            raise ValueError('This booking cannot be cancelled.')

        if booking.status == 'CONFIRMED':
            if not user or not user.is_staff:
                raise ValueError('Only staff can cancel confirmed bookings.')
            if not reason or not reason.strip():
                raise ValueError('A cancellation reason is required for confirmed bookings.')

        with transaction.atomic():
            booking.status = 'CANCELLED'
            booking.cancelled_at = timezone.now()
            if user:
                booking.cancelled_by = user
            if reason:
                booking.cancellation_reason = reason
            booking.save()

            cls._log(
                booking, 'CANCELLED', user=user, request=request,
                notes=reason,
            )

        notifications.notify_booking_cancelled(booking)
        _safe_fms_dispatch('dispatch_cancellation', booking)
        _safe_carrier_dispatch('dispatch_carrier_cancellation', booking)

    @classmethod
    def resubmit_booking(cls, booking, user=None, request=None):
        """Return a REJECTED booking to DRAFT so the customer can revise and resubmit."""
        if booking.status != 'REJECTED':
            raise ValueError('Only rejected bookings can be resubmitted.')

        with transaction.atomic():
            booking.status = 'DRAFT'
            # Clear rejection fields but keep them in audit log
            booking.rejected_at = None
            booking.rejected_by = None
            booking.rejection_reason = ''
            booking.save()

            cls._log(booking, 'RESUBMITTED', user=user, request=request,
                     notes='Booking returned to draft for revision')

        notifications.notify_booking_resubmitted(booking)

    # ─── Documents ────────────────────────────────────────────────────

    @classmethod
    def upload_document(cls, booking, form, user, request=None):
        """
        Upload a document to a booking.

        Returns the new BookingDocument instance.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Documents can only be uploaded to active bookings.')

        if not form.is_valid():
            raise ValueError('Invalid document data.')

        uploaded_file = form.cleaned_data['file']

        # Validate file size (enforced here for non-form channels too)
        err = validators.validate_file_size(uploaded_file.size)
        if err:
            raise ValueError(err)

        with transaction.atomic():
            document = form.save(commit=False)
            document.booking = booking
            document.uploaded_by = user
            document.original_filename = uploaded_file.name
            document.file_size = uploaded_file.size
            document.save()

            cls._log(
                booking, 'DOCUMENT_UPLOADED', user=user, request=request,
                new_value={
                    'document_type': document.document_type,
                    'filename': document.original_filename,
                    'size': document.file_size,
                },
            )

        return document

    @classmethod
    def delete_document(cls, booking, document, user, request=None):
        """Delete a document from a DRAFT booking."""
        if booking.status != 'DRAFT':
            raise ValueError('Documents can only be deleted on draft bookings.')

        filename = document.original_filename

        with transaction.atomic():
            document.file.delete()
            document.delete()

            cls._log(
                booking, 'DOCUMENT_DELETED', user=user, request=request,
                old_value={'filename': filename},
            )

    # ─── Parties ──────────────────────────────────────────────────────

    @classmethod
    def add_party_to_booking(cls, booking, party, role=None, user=None, request=None):
        """
        Add a party to a booking by creating a snapshot.

        Returns the new BookingParty instance.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Parties can only be added to active bookings.')

        with transaction.atomic():
            booking_party = BookingParty.create_from_party(booking, party, role)

            cls._log(
                booking, 'PARTY_ADDED', user=user, request=request,
                new_value={
                    'role': booking_party.role,
                    'company_name': booking_party.company_name,
                },
            )

        return booking_party

    @classmethod
    def remove_party_from_booking(cls, booking, booking_party, user=None, request=None):
        """Remove a party assignment from a booking."""
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Parties can only be removed from active bookings.')

        old = {
            'role': booking_party.role,
            'company_name': booking_party.company_name,
        }

        with transaction.atomic():
            booking_party.delete()

            cls._log(
                booking, 'PARTY_REMOVED', user=user, request=request,
                old_value=old,
            )
