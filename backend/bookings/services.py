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
    ShipmentMilestone, Consolidation,
)
from . import notifications, validators
from .workflow_engine import WorkflowEngine

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
            'service_type': booking.service_type,
            'move_type': booking.move_type,
        }

    @staticmethod
    def _item_snapshot(item):
        """Return a JSON-safe dict of a cargo item for audit diffs."""
        return {
            'id': item.pk,
            'description': item.description,
            'package_type': item.package_type,
            'quantity': item.quantity,
            'weight_kg': str(item.weight_kg),
            'hs_code': item.hs_code,
            'volume_cbm': str(item.volume_cbm) if item.volume_cbm else None,
            'length_cm': str(item.length_cm) if item.length_cm else None,
            'width_cm': str(item.width_cm) if item.width_cm else None,
            'height_cm': str(item.height_cm) if item.height_cm else None,
            'marks_and_numbers': item.marks_and_numbers,
            'is_hazardous': item.is_hazardous,
            'un_number': item.un_number,
            'imo_class': item.imo_class,
            'country_of_origin': item.country_of_origin,
        }

    # ─── Workflow helpers ─────────────────────────────────────────────

    @staticmethod
    def _validate_workflow_transition(booking, to_status, user=None):
        """Check workflow allows the transition. Raises ValueError if blocked."""
        allowed, error = WorkflowEngine.validate_transition(booking, to_status, user)
        if not allowed:
            raise ValueError(error)

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
            WorkflowEngine.assign_workflow_to_booking(booking, customer)
            booking.save()

            formset.instance = booking
            formset.save()

            booking.recalculate_totals()

            cls._log(
                booking, 'CREATED', user=user, request=request,
                new_value=cls._booking_snapshot(booking),
            )

            for item in booking.items.all():
                cls._log(
                    booking, 'ITEM_ADDED', user=user, request=request,
                    new_value=cls._item_snapshot(item),
                )

        return booking

    # ─── Update ───────────────────────────────────────────────────────

    @classmethod
    def update_booking(cls, booking, form, formset, user, request=None):
        """
        Update an existing DRAFT or SUBMITTED booking from validated form + formset.

        Returns the updated Booking instance.
        Raises ValueError if booking is not DRAFT/SUBMITTED or forms are invalid.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('Only draft or submitted bookings can be edited.')

        if not form.is_valid() or not formset.is_valid():
            raise ValueError('Invalid form data.')

        with transaction.atomic():
            old = cls._booking_snapshot(booking)
            old_items = {item.pk: cls._item_snapshot(item) for item in booking.items.all()}

            form.save()
            formset.save()
            booking.refresh_from_db()
            booking.recalculate_totals()

            cls._log(
                booking, 'UPDATED', user=user, request=request,
                old_value=old,
                new_value=cls._booking_snapshot(booking),
            )

            new_items = {item.pk: cls._item_snapshot(item) for item in booking.items.all()}

            # Removed items
            for pk in old_items:
                if pk not in new_items:
                    cls._log(
                        booking, 'ITEM_REMOVED', user=user, request=request,
                        old_value=old_items[pk],
                    )

            # Added items
            for pk in new_items:
                if pk not in old_items:
                    cls._log(
                        booking, 'ITEM_ADDED', user=user, request=request,
                        new_value=new_items[pk],
                    )

            # Updated items
            for pk in old_items:
                if pk in new_items and old_items[pk] != new_items[pk]:
                    cls._log(
                        booking, 'ITEM_UPDATED', user=user, request=request,
                        old_value=old_items[pk],
                        new_value=new_items[pk],
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
                service_type=data.get('service_type', ''),
                move_type=data.get('move_type', ''),
            )
            WorkflowEngine.assign_workflow_to_booking(booking, customer)
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

            for item in booking.items.all():
                cls._log(
                    booking, 'ITEM_ADDED', user=user, request=request,
                    new_value=cls._item_snapshot(item),
                )

        return booking

    @classmethod
    def update_booking_from_data(cls, booking, data, user, request=None,
                                  items_data=None):
        """
        Update a DRAFT or SUBMITTED booking from validated data dicts.

        Args:
            booking: Existing Booking instance (must be DRAFT or SUBMITTED).
            data: dict of fields to update. Only provided keys are changed.
            user: User performing the action.
            request: Optional HttpRequest for audit logging.
            items_data: If provided, replaces all existing items.

        Returns the updated Booking instance.
        Raises ValueError if booking is not DRAFT or SUBMITTED.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('Only draft or submitted bookings can be edited.')

        with transaction.atomic():
            old = cls._booking_snapshot(booking)

            updatable_fields = [
                'transport_mode', 'origin_port', 'destination_port',
                'cargo_ready_date', 'container_type', 'container_count',
                'incoterms', 'incoterms_location', 'commodity_description',
                'is_hazardous', 'external_reference', 'special_instructions',
                'chargeable_weight_kg', 'flight_number', 'service_type',
                'move_type',
            ]
            for field in updatable_fields:
                if field in data:
                    setattr(booking, field, data[field])

            booking.save()

            if items_data is not None:
                # Snapshot old items before deletion
                old_items = [cls._item_snapshot(item) for item in booking.items.all()]
                booking.items.all().delete()

                for old_snap in old_items:
                    cls._log(
                        booking, 'ITEM_REMOVED', user=user, request=request,
                        old_value=old_snap,
                    )

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

                for item in booking.items.all():
                    cls._log(
                        booking, 'ITEM_ADDED', user=user, request=request,
                        new_value=cls._item_snapshot(item),
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
        cls._validate_workflow_transition(booking, 'SUBMITTED', user)
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
        cls._validate_workflow_transition(booking, 'CONFIRMED', user)
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
    def customer_approve_booking(cls, booking, user=None, request=None):
        """Customer approves a CONFIRMED booking, moving it to PACKING."""
        cls._validate_workflow_transition(booking, 'PACKING', user)
        if booking.status != 'CONFIRMED':
            raise ValueError('Only confirmed bookings can be approved by the customer.')

        with transaction.atomic():
            booking.status = 'PACKING'
            booking.packing_at = timezone.now()
            booking.customer_approved_by = user
            booking.save()

            cls._log(booking, 'CUSTOMER_APPROVED', user=user, request=request)

        notifications.notify_booking_customer_approved(booking)

    @classmethod
    def customer_reject_booking(cls, booking, user=None, reason='', request=None):
        """Customer rejects a CONFIRMED booking."""
        cls._validate_workflow_transition(booking, 'CUSTOMER_REJECTED', user)
        if booking.status != 'CONFIRMED':
            raise ValueError('Only confirmed bookings can be rejected by the customer.')

        with transaction.atomic():
            booking.status = 'CUSTOMER_REJECTED'
            booking.customer_rejected_at = timezone.now()
            booking.customer_rejected_by = user
            booking.customer_rejection_reason = reason
            booking.save()

            cls._log(
                booking, 'CUSTOMER_REJECTED', user=user, request=request,
                notes=reason,
            )

        notifications.notify_booking_customer_rejected(booking)

    @classmethod
    def reconfirm_booking(cls, booking, user=None, request=None):
        """Return a CUSTOMER_REJECTED booking to CONFIRMED (ops re-proposes)."""
        cls._validate_workflow_transition(booking, 'CONFIRMED', user)
        if booking.status != 'CUSTOMER_REJECTED':
            raise ValueError('Only customer-rejected bookings can be re-confirmed.')

        with transaction.atomic():
            booking.status = 'CONFIRMED'
            booking.customer_rejected_at = None
            booking.customer_rejected_by = None
            booking.customer_rejection_reason = ''
            booking.confirmed_at = timezone.now()
            booking.confirmed_by = user
            booking.save()

            cls._log(booking, 'RECONFIRMED', user=user, request=request,
                     notes='Booking re-confirmed after customer rejection')

        notifications.notify_booking_confirmed(booking)

    @classmethod
    def reject_booking(cls, booking, user=None, reason='', request=None):
        """Reject a booking (ops action). Allowed from most active statuses."""
        cls._validate_workflow_transition(booking, 'REJECTED', user)
        allowed = ('SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED')
        if booking.status not in allowed:
            raise ValueError('This booking cannot be rejected.')

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
        """Mark a PACKING booking as in transit."""
        cls._validate_workflow_transition(booking, 'IN_TRANSIT', user)
        if booking.status != 'PACKING':
            raise ValueError('Only bookings in packing status can be marked in transit.')

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
    def mark_arrived(cls, booking, user=None, request=None,
                     actual_arrival_date=None):
        """Mark an IN_TRANSIT booking as arrived at destination."""
        cls._validate_workflow_transition(booking, 'ARRIVED', user)
        if booking.status != 'IN_TRANSIT':
            raise ValueError('Only in-transit bookings can be marked as arrived.')

        with transaction.atomic():
            booking.status = 'ARRIVED'
            booking.arrived_at = timezone.now()
            if actual_arrival_date:
                booking.actual_arrival_date = actual_arrival_date
            booking.save()

            cls._log(booking, 'ARRIVED', user=user, request=request)

        notifications.notify_booking_arrived(booking)
        _safe_fms_dispatch('dispatch_milestone_update', booking, 'ARRIVED')

    @classmethod
    def complete_booking(cls, booking, user=None, request=None,
                         actual_arrival_date=None):
        """Mark an IN_TRANSIT or ARRIVED booking as completed."""
        cls._validate_workflow_transition(booking, 'COMPLETED', user)
        if booking.status not in ('IN_TRANSIT', 'ARRIVED'):
            raise ValueError('Only in-transit or arrived bookings can be completed.')

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
        cls._validate_workflow_transition(booking, 'CONFIRMED', user)
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
    def record_milestone(cls, booking, milestone_type, occurred_at, location='',
                         notes='', user=None, request=None):
        """Record an operational milestone on a booking."""
        with transaction.atomic():
            milestone = ShipmentMilestone.objects.create(
                booking=booking,
                milestone_type=milestone_type,
                occurred_at=occurred_at,
                location=location,
                notes=notes,
                recorded_by=user,
            )
            cls._log(
                booking, 'UPDATED', user=user, request=request,
                notes=f'Milestone recorded: {milestone.get_milestone_type_display()}',
            )
        return milestone

    @classmethod
    def update_carrier_details(cls, booking, form, user=None, request=None):
        """Update carrier details on a CONFIRMED, PACKING, IN_TRANSIT, or ARRIVED booking."""
        if booking.status not in ('CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
            raise ValueError('Carrier details can only be updated on confirmed, packing, in-transit, or arrived bookings.')

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
        if booking.status not in ('SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
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
        if booking.status not in ('CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
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
        """Cancel a DRAFT, SUBMITTED, CONFIRMED, or PACKING booking.

        Cancelling a CONFIRMED or PACKING booking requires a reason and is staff-only.
        """
        cls._validate_workflow_transition(booking, 'CANCELLED', user)
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'PACKING', 'CUSTOMER_REJECTED'):
            raise ValueError('This booking cannot be cancelled.')

        if booking.status in ('CONFIRMED', 'PACKING', 'CUSTOMER_REJECTED'):
            if not user or not user.is_staff:
                raise ValueError('Only staff can cancel confirmed, packing, or customer-rejected bookings.')
            if not reason or not reason.strip():
                raise ValueError('A cancellation reason is required.')

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
        cls._validate_workflow_transition(booking, 'DRAFT', user)
        if booking.status != 'REJECTED':
            raise ValueError('Only rejected bookings can be resubmitted.')

        with transaction.atomic():
            booking.status = 'DRAFT'
            # Clear rejection fields but keep them in audit log
            booking.rejected_at = None
            booking.rejected_by = None
            booking.rejection_reason = ''
            # Clear stale lifecycle timestamps so tracking timeline resets
            booking.submitted_at = None
            booking.confirmed_at = None
            booking.confirmed_by = None
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
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
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
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
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
        if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED'):
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

    # ── Consolidation Methods ──────────────────────────────────────

    @classmethod
    def create_consolidation(cls, customer, booking_ids, user, request=None, notes=''):
        """Create a consolidation and assign bookings to it."""
        if not booking_ids:
            raise ValueError('At least one booking is required to create a consolidation.')

        VALID_STATUSES = ('SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED', 'COMPLETED')

        with transaction.atomic():
            bookings = list(
                Booking.objects.select_for_update()
                .filter(pk__in=booking_ids, customer=customer)
            )
            if len(bookings) != len(booking_ids):
                raise ValueError('One or more bookings not found for this customer.')

            for b in bookings:
                if b.status not in VALID_STATUSES:
                    raise ValueError(
                        f'Booking {b.booking_number} is in {b.get_status_display()} status '
                        f'and cannot be consolidated.'
                    )
                if b.consolidation_id:
                    raise ValueError(
                        f'Booking {b.booking_number} is already in consolidation '
                        f'{b.consolidation.consolidation_number}.'
                    )

            consolidation = Consolidation(
                customer=customer,
                notes=notes,
                created_by=user,
            )
            consolidation.save()

            for b in bookings:
                b.consolidation = consolidation
                b.save(update_fields=['consolidation'])
                cls._log(
                    b, 'CONSOLIDATED', user=user, request=request,
                    new_value={'consolidation_number': consolidation.consolidation_number},
                )

        return consolidation

    @classmethod
    def add_booking_to_consolidation(cls, consolidation, booking, user, request=None):
        """Add a single booking to an existing consolidation."""
        VALID_STATUSES = ('SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED', 'COMPLETED')

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            consolidation = Consolidation.objects.select_for_update().get(pk=consolidation.pk)

            if consolidation.status != 'OPEN':
                raise ValueError('Cannot add bookings to a closed consolidation.')
            if booking.customer_id != consolidation.customer_id:
                raise ValueError('Booking must belong to the same customer as the consolidation.')
            if booking.status not in VALID_STATUSES:
                raise ValueError(f'Booking {booking.booking_number} cannot be consolidated in its current status.')
            if booking.consolidation_id:
                raise ValueError(f'Booking {booking.booking_number} is already consolidated.')

            booking.consolidation = consolidation
            booking.save(update_fields=['consolidation'])
            cls._log(
                booking, 'CONSOLIDATED', user=user, request=request,
                new_value={'consolidation_number': consolidation.consolidation_number},
            )

    @classmethod
    def remove_booking_from_consolidation(cls, consolidation, booking, user, request=None):
        """Remove a booking from a consolidation."""
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            consolidation = Consolidation.objects.select_for_update().get(pk=consolidation.pk)

            if consolidation.status != 'OPEN':
                raise ValueError('Cannot remove bookings from a closed consolidation.')
            if booking.consolidation_id != consolidation.pk:
                raise ValueError('Booking is not in this consolidation.')

            old_number = consolidation.consolidation_number
            booking.consolidation = None
            booking.save(update_fields=['consolidation'])
            cls._log(
                booking, 'UNCONSOLIDATED', user=user, request=request,
                old_value={'consolidation_number': old_number},
            )

    @classmethod
    def close_consolidation(cls, consolidation, user, request=None):
        """Close a consolidation (no more bookings can be added/removed)."""
        if consolidation.status != 'OPEN':
            raise ValueError('Consolidation is already closed.')

        with transaction.atomic():
            consolidation.status = 'CLOSED'
            consolidation.save(update_fields=['status', 'updated_at'])

            for b in consolidation.bookings.all():
                cls._log(
                    b, 'CONSOLIDATED', user=user, request=request,
                    new_value={'consolidation_closed': consolidation.consolidation_number},
                )
