"""
Service layer for the freight booking system.

ALL booking mutations (create, edit, submit, cancel, etc.) go through
BookingService. This ensures:
  1. Consistent validation via validators.py
  2. Automatic audit logging
  3. Single entry point for web, API, EDI, and CSV channels

Views and serializers should NEVER mutate Booking/BookingItem directly.
"""
from django.db import transaction
from django.utils import timezone

from .models import (
    Booking, BookingItem, BookingDocument, BookingParty, Party, AuditLog,
)
from . import notifications, validators


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
            ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            if not ip:
                ip = request.META.get('REMOTE_ADDR')
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

    # ─── Status transitions ───────────────────────────────────────────

    @classmethod
    def submit_booking(cls, booking, user, request=None):
        """Submit a DRAFT booking. Raises ValueError on failure."""
        if booking.status != 'DRAFT':
            raise ValueError('Only draft bookings can be submitted.')
        if not booking.items.exists():
            raise ValueError('Cannot submit a booking with no cargo items.')

        with transaction.atomic():
            booking.recalculate_totals()
            booking.status = 'SUBMITTED'
            booking.submitted_at = timezone.now()
            booking.save()

            cls._log(booking, 'SUBMITTED', user=user, request=request)

    @classmethod
    def confirm_booking(cls, booking, user=None, request=None):
        """Confirm a SUBMITTED booking (operations action)."""
        if booking.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be confirmed.')

        with transaction.atomic():
            booking.status = 'CONFIRMED'
            booking.confirmed_at = timezone.now()
            booking.save()

            cls._log(booking, 'CONFIRMED', user=user, request=request)

        notifications.notify_booking_confirmed(booking)

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
    def mark_in_transit(cls, booking, user=None, request=None):
        """Mark a CONFIRMED booking as in transit."""
        if booking.status != 'CONFIRMED':
            raise ValueError('Only confirmed bookings can be marked in transit.')

        with transaction.atomic():
            booking.status = 'IN_TRANSIT'
            booking.save()

            cls._log(booking, 'IN_TRANSIT', user=user, request=request)

        notifications.notify_booking_in_transit(booking)

    @classmethod
    def complete_booking(cls, booking, user=None, request=None):
        """Mark an IN_TRANSIT booking as completed."""
        if booking.status != 'IN_TRANSIT':
            raise ValueError('Only in-transit bookings can be completed.')

        with transaction.atomic():
            booking.status = 'COMPLETED'
            booking.completed_at = timezone.now()
            booking.save()

            cls._log(booking, 'COMPLETED', user=user, request=request)

        notifications.notify_booking_completed(booking)

    @classmethod
    def confirm_booking_with_carrier(cls, booking, carrier_form, user=None, request=None):
        """Confirm a SUBMITTED booking and save carrier details in one transaction."""
        if booking.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be confirmed.')

        with transaction.atomic():
            if carrier_form and carrier_form.is_valid():
                for field in carrier_form.cleaned_data:
                    setattr(booking, field, carrier_form.cleaned_data[field])

            booking.status = 'CONFIRMED'
            booking.confirmed_at = timezone.now()
            booking.save()

            cls._log(booking, 'CONFIRMED', user=user, request=request)

        notifications.notify_booking_confirmed(booking)
        return booking

    @classmethod
    def update_carrier_details(cls, booking, form, user=None, request=None):
        """Update carrier details on a CONFIRMED or IN_TRANSIT booking."""
        if booking.status not in ('CONFIRMED', 'IN_TRANSIT'):
            raise ValueError('Carrier details can only be updated on confirmed or in-transit bookings.')

        if not form.is_valid():
            raise ValueError('Invalid carrier details.')

        old = {
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

    @classmethod
    def cancel_booking(cls, booking, user=None, request=None):
        """Cancel a DRAFT or SUBMITTED booking."""
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('This booking cannot be cancelled.')

        with transaction.atomic():
            booking.status = 'CANCELLED'
            booking.cancelled_at = timezone.now()
            if user:
                booking.cancelled_by = user
            booking.save()

            cls._log(booking, 'CANCELLED', user=user, request=request)

    # ─── Documents ────────────────────────────────────────────────────

    @classmethod
    def upload_document(cls, booking, form, user, request=None):
        """
        Upload a document to a booking.

        Returns the new BookingDocument instance.
        """
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('Documents can only be uploaded to draft or submitted bookings.')

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
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('Parties can only be added to draft or submitted bookings.')

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
        if booking.status not in ('DRAFT', 'SUBMITTED'):
            raise ValueError('Parties can only be removed from draft or submitted bookings.')

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
