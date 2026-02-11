"""
Tests for bookings.services.BookingService — all booking mutations.

Uses TestCase (needs database). Notification calls are mocked.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, RequestFactory
from django.utils import timezone

from bookings.models import Booking, BookingItem, BookingDocument, BookingParty, AuditLog
from bookings.services import BookingService
from bookings.forms import (
    BookingForm, BookingItemFormSet, CarrierDetailsForm,
    BookingDocumentForm,
)
from bookings.tests.helpers import (
    create_customer, create_user, create_port, create_container_type,
    create_booking, create_booking_item, create_party, create_document,
)


class ServiceTestBase(TestCase):
    """Shared setup for all service tests."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)
        cls.staff = create_user(username='staff', is_staff=True)
        cls.port_origin = create_port()
        cls.port_dest = create_port(code='CNSHA', name='Shanghai', country='CN')
        cls.container_type = create_container_type()
        cls.factory = RequestFactory()

    def _make_request(self, user=None):
        request = self.factory.get('/')
        request.user = user or self.user
        request.META['REMOTE_ADDR'] = '127.0.0.1'
        request.META['HTTP_USER_AGENT'] = 'TestBrowser/1.0'
        return request

    def _valid_booking_data(self, **overrides):
        data = {
            'transport_mode': 'SEA_FCL',
            'origin_port': self.port_origin.pk,
            'destination_port': self.port_dest.pk,
            'cargo_ready_date': (date.today() + timedelta(days=14)).isoformat(),
            'container_type': self.container_type.pk,
            'container_count': 2,
            'incoterms': 'FOB',
            'incoterms_location': '',
            'commodity_description': 'Electronics',
            'is_hazardous': False,
            'external_reference': '',
            'special_instructions': '',
        }
        data.update(overrides)
        return data

    def _valid_item_data(self, prefix='items', total=1, **overrides):
        data = {
            f'{prefix}-TOTAL_FORMS': str(total),
            f'{prefix}-INITIAL_FORMS': '0',
            f'{prefix}-MIN_NUM_FORMS': '1',
            f'{prefix}-MAX_NUM_FORMS': '1000',
        }
        for i in range(total):
            item_defaults = {
                f'{prefix}-{i}-description': 'Test Cargo',
                f'{prefix}-{i}-package_type': 'CARTON',
                f'{prefix}-{i}-quantity': '10',
                f'{prefix}-{i}-weight_kg': '100.00',
                f'{prefix}-{i}-hs_code': '',
                f'{prefix}-{i}-volume_cbm': '',
                f'{prefix}-{i}-length_cm': '',
                f'{prefix}-{i}-width_cm': '',
                f'{prefix}-{i}-height_cm': '',
                f'{prefix}-{i}-marks_and_numbers': '',
                f'{prefix}-{i}-is_hazardous': '',
                f'{prefix}-{i}-un_number': '',
                f'{prefix}-{i}-imo_class': '',
                f'{prefix}-{i}-country_of_origin': '',
            }
            item_defaults.update({k: v for k, v in overrides.items() if k.startswith(f'{prefix}-{i}-')})
            data.update(item_defaults)
        return data


# ─── Create ─────────────────────────────────────────────────────────


class TestCreateBooking(ServiceTestBase):

    def test_create_booking_success(self):
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        form = BookingForm(data)
        formset = BookingItemFormSet(data, prefix='items')
        booking = BookingService.create_booking(
            form, formset, self.customer, self.user,
        )
        self.assertEqual(booking.status, 'DRAFT')
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.created_by, self.user)
        self.assertTrue(booking.booking_number.startswith('BK-'))
        self.assertEqual(booking.items.count(), 1)

    def test_create_booking_sets_source_channel(self):
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        form = BookingForm(data)
        formset = BookingItemFormSet(data, prefix='items')
        booking = BookingService.create_booking(
            form, formset, self.customer, self.user, source_channel='API',
        )
        self.assertEqual(booking.source_channel, 'API')

    def test_create_booking_creates_audit_log(self):
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        form = BookingForm(data)
        formset = BookingItemFormSet(data, prefix='items')
        request = self._make_request()
        booking = BookingService.create_booking(
            form, formset, self.customer, self.user, request=request,
        )
        log = AuditLog.objects.filter(booking=booking, action='CREATED').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.performed_by, self.user)
        self.assertIsNotNone(log.new_value)

    def test_create_booking_invalid_form_raises(self):
        data = {**self._valid_booking_data(origin_port=''), **self._valid_item_data()}
        form = BookingForm(data)
        formset = BookingItemFormSet(data, prefix='items')
        with self.assertRaises(ValueError):
            BookingService.create_booking(form, formset, self.customer, self.user)

    def test_create_booking_recalculates_totals(self):
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        form = BookingForm(data)
        formset = BookingItemFormSet(data, prefix='items')
        booking = BookingService.create_booking(
            form, formset, self.customer, self.user,
        )
        self.assertEqual(booking.total_weight_kg, Decimal('100.00'))


# ─── Update ─────────────────────────────────────────────────────────


class TestUpdateBooking(ServiceTestBase):

    def test_update_draft_booking(self):
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        data = {**self._valid_booking_data(container_count=5), **self._valid_item_data()}
        data['items-INITIAL_FORMS'] = '1'
        data['items-0-id'] = str(booking.items.first().pk)
        form = BookingForm(data, instance=booking)
        formset = BookingItemFormSet(data, instance=booking, prefix='items')
        updated = BookingService.update_booking(booking, form, formset, self.user)
        self.assertEqual(updated.container_count, 5)

    def test_update_non_draft_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        create_booking_item(booking)
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        form = BookingForm(data, instance=booking)
        formset = BookingItemFormSet(data, instance=booking, prefix='items')
        with self.assertRaises(ValueError):
            BookingService.update_booking(booking, form, formset, self.user)

    def test_update_creates_audit_log_with_old_new(self):
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        data = {**self._valid_booking_data(), **self._valid_item_data()}
        data['items-INITIAL_FORMS'] = '1'
        data['items-0-id'] = str(booking.items.first().pk)
        form = BookingForm(data, instance=booking)
        formset = BookingItemFormSet(data, instance=booking, prefix='items')
        BookingService.update_booking(booking, form, formset, self.user)
        log = AuditLog.objects.filter(booking=booking, action='UPDATED').first()
        self.assertIsNotNone(log)
        self.assertIsNotNone(log.old_value)
        self.assertIsNotNone(log.new_value)


# ─── Status transitions ─────────────────────────────────────────────


class TestSubmitBooking(ServiceTestBase):

    def test_submit_success(self):
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        BookingService.submit_booking(booking, self.user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'SUBMITTED')
        self.assertIsNotNone(booking.submitted_at)

    def test_submit_no_items_raises(self):
        booking = create_booking(self.customer, self.user)
        with self.assertRaises(ValueError):
            BookingService.submit_booking(booking, self.user)

    def test_submit_non_draft_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        with self.assertRaises(ValueError):
            BookingService.submit_booking(booking, self.user)

    def test_submit_creates_audit_log(self):
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        BookingService.submit_booking(booking, self.user)
        log = AuditLog.objects.filter(booking=booking, action='SUBMITTED').first()
        self.assertIsNotNone(log)


class TestConfirmBooking(ServiceTestBase):

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_confirm_success(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        BookingService.confirm_booking(booking, user=self.staff)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CONFIRMED')
        self.assertEqual(booking.confirmed_by, self.staff)
        self.assertIsNotNone(booking.confirmed_at)
        mock_notify.assert_called_once_with(booking)

    def test_confirm_non_submitted_raises(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        with self.assertRaises(ValueError):
            BookingService.confirm_booking(booking)

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_confirm_creates_audit_log(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        BookingService.confirm_booking(booking, user=self.staff)
        log = AuditLog.objects.filter(booking=booking, action='CONFIRMED').first()
        self.assertIsNotNone(log)


class TestRejectBooking(ServiceTestBase):

    @patch('bookings.services.notifications.notify_booking_rejected')
    def test_reject_success(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        BookingService.reject_booking(booking, user=self.staff, reason='Bad docs')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'REJECTED')
        self.assertEqual(booking.rejection_reason, 'Bad docs')
        self.assertEqual(booking.rejected_by, self.staff)
        mock_notify.assert_called_once_with(booking)

    def test_reject_non_submitted_raises(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        with self.assertRaises(ValueError):
            BookingService.reject_booking(booking)

    @patch('bookings.services.notifications.notify_booking_rejected')
    def test_reject_creates_audit_log_with_reason(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        BookingService.reject_booking(booking, user=self.staff, reason='Missing packing list')
        log = AuditLog.objects.filter(booking=booking, action='REJECTED').first()
        self.assertIsNotNone(log)
        self.assertIn('Missing packing list', log.notes)


class TestMarkInTransit(ServiceTestBase):

    @patch('bookings.services.notifications.notify_booking_in_transit')
    def test_in_transit_success(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        BookingService.mark_in_transit(booking, user=self.staff)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'IN_TRANSIT')
        self.assertIsNotNone(booking.in_transit_at)
        mock_notify.assert_called_once_with(booking)

    @patch('bookings.services.notifications.notify_booking_in_transit')
    def test_in_transit_with_departure_date(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        dep_date = date.today()
        BookingService.mark_in_transit(booking, actual_departure_date=dep_date)
        booking.refresh_from_db()
        self.assertEqual(booking.actual_departure_date, dep_date)

    def test_in_transit_non_confirmed_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        with self.assertRaises(ValueError):
            BookingService.mark_in_transit(booking)


class TestCompleteBooking(ServiceTestBase):

    @patch('bookings.services.notifications.notify_booking_completed')
    def test_complete_success(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='IN_TRANSIT')
        BookingService.complete_booking(booking, user=self.staff)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'COMPLETED')
        self.assertIsNotNone(booking.completed_at)
        mock_notify.assert_called_once_with(booking)

    @patch('bookings.services.notifications.notify_booking_completed')
    def test_complete_with_arrival_date(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='IN_TRANSIT')
        arr_date = date.today()
        BookingService.complete_booking(booking, actual_arrival_date=arr_date)
        booking.refresh_from_db()
        self.assertEqual(booking.actual_arrival_date, arr_date)

    def test_complete_non_in_transit_raises(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        with self.assertRaises(ValueError):
            BookingService.complete_booking(booking)


class TestCancelBooking(ServiceTestBase):

    def test_cancel_draft(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        BookingService.cancel_booking(booking, user=self.user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(booking.cancelled_by, self.user)

    def test_cancel_submitted(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        BookingService.cancel_booking(booking, user=self.user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_confirmed_with_reason(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        BookingService.cancel_booking(booking, user=self.staff, reason='Customer request')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(booking.cancellation_reason, 'Customer request')

    def test_cancel_in_transit_raises(self):
        booking = create_booking(self.customer, self.user, status='IN_TRANSIT')
        with self.assertRaises(ValueError):
            BookingService.cancel_booking(booking)

    def test_cancel_creates_audit_log(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        BookingService.cancel_booking(booking, user=self.user, reason='Test')
        log = AuditLog.objects.filter(booking=booking, action='CANCELLED').first()
        self.assertIsNotNone(log)
        self.assertIn('Test', log.notes)


class TestResubmitBooking(ServiceTestBase):

    def test_resubmit_success(self):
        booking = create_booking(self.customer, self.user, status='REJECTED')
        booking.rejected_at = timezone.now()
        booking.rejected_by = self.staff
        booking.rejection_reason = 'Bad docs'
        booking.save()
        BookingService.resubmit_booking(booking, user=self.user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'DRAFT')
        self.assertIsNone(booking.rejected_at)
        self.assertIsNone(booking.rejected_by)
        self.assertEqual(booking.rejection_reason, '')

    def test_resubmit_non_rejected_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        with self.assertRaises(ValueError):
            BookingService.resubmit_booking(booking)

    def test_resubmit_creates_audit_log(self):
        booking = create_booking(self.customer, self.user, status='REJECTED')
        BookingService.resubmit_booking(booking, user=self.user)
        log = AuditLog.objects.filter(booking=booking, action='RESUBMITTED').first()
        self.assertIsNotNone(log)


# ─── Carrier operations ─────────────────────────────────────────────


class TestConfirmWithCarrier(ServiceTestBase):

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_confirm_with_carrier_details(self, mock_notify):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        carrier_data = {
            'carrier_name': 'Maersk',
            'vessel_name': 'Maersk Elba',
            'voyage_number': '428W',
            'cargo_cutoff_date': '',
            'etd': (date.today() + timedelta(days=10)).isoformat(),
            'eta': (date.today() + timedelta(days=30)).isoformat(),
            'carrier_booking_ref': 'MRK-001',
            'contract_number': 'CNT-123',
        }
        form = CarrierDetailsForm(carrier_data, instance=booking)
        result = BookingService.confirm_booking_with_carrier(
            booking, form, user=self.staff,
        )
        result.refresh_from_db()
        self.assertEqual(result.status, 'CONFIRMED')
        self.assertEqual(result.carrier_name, 'Maersk')
        self.assertEqual(result.vessel_name, 'Maersk Elba')
        mock_notify.assert_called_once()

    def test_confirm_with_invalid_carrier_form_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        # ETA before ETD should make form invalid
        carrier_data = {
            'carrier_name': 'Maersk',
            'vessel_name': '',
            'voyage_number': '',
            'cargo_cutoff_date': '',
            'etd': (date.today() + timedelta(days=30)).isoformat(),
            'eta': (date.today() + timedelta(days=10)).isoformat(),
            'carrier_booking_ref': '',
            'contract_number': '',
        }
        form = CarrierDetailsForm(carrier_data, instance=booking)
        with self.assertRaises(ValueError):
            BookingService.confirm_booking_with_carrier(booking, form, user=self.staff)

    def test_confirm_non_submitted_raises(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        form = CarrierDetailsForm({
            'carrier_name': '', 'vessel_name': '', 'voyage_number': '',
            'cargo_cutoff_date': '', 'etd': '', 'eta': '',
            'carrier_booking_ref': '', 'contract_number': '',
        }, instance=booking)
        with self.assertRaises(ValueError):
            BookingService.confirm_booking_with_carrier(booking, form)


class TestUpdateCarrierDetails(ServiceTestBase):

    def test_update_carrier_on_confirmed(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        data = {
            'carrier_name': 'MSC',
            'vessel_name': 'MSC Anna',
            'voyage_number': '123E',
            'cargo_cutoff_date': '',
            'etd': (date.today() + timedelta(days=5)).isoformat(),
            'eta': (date.today() + timedelta(days=25)).isoformat(),
            'carrier_booking_ref': '',
            'contract_number': '',
        }
        form = CarrierDetailsForm(data, instance=booking)
        result = BookingService.update_carrier_details(booking, form, user=self.staff)
        result.refresh_from_db()
        self.assertEqual(result.carrier_name, 'MSC')
        self.assertEqual(result.vessel_name, 'MSC Anna')

    def test_update_carrier_on_in_transit(self):
        booking = create_booking(self.customer, self.user, status='IN_TRANSIT')
        data = {
            'carrier_name': 'CMA CGM', 'vessel_name': '', 'voyage_number': '',
            'cargo_cutoff_date': '', 'etd': '', 'eta': '',
            'carrier_booking_ref': '', 'contract_number': '',
        }
        form = CarrierDetailsForm(data, instance=booking)
        result = BookingService.update_carrier_details(booking, form, user=self.staff)
        result.refresh_from_db()
        self.assertEqual(result.carrier_name, 'CMA CGM')

    def test_update_carrier_on_draft_raises(self):
        booking = create_booking(self.customer, self.user, status='DRAFT')
        data = {
            'carrier_name': 'Test', 'vessel_name': '', 'voyage_number': '',
            'cargo_cutoff_date': '', 'etd': '', 'eta': '',
            'carrier_booking_ref': '', 'contract_number': '',
        }
        form = CarrierDetailsForm(data, instance=booking)
        with self.assertRaises(ValueError):
            BookingService.update_carrier_details(booking, form)

    def test_update_carrier_creates_audit_log(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        data = {
            'carrier_name': 'Hapag', 'vessel_name': '', 'voyage_number': '',
            'cargo_cutoff_date': '', 'etd': '', 'eta': '',
            'carrier_booking_ref': '', 'contract_number': '',
        }
        form = CarrierDetailsForm(data, instance=booking)
        BookingService.update_carrier_details(booking, form, user=self.staff)
        log = AuditLog.objects.filter(booking=booking, action='UPDATED').first()
        self.assertIsNotNone(log)
        self.assertIn('Carrier details', log.notes)


# ─── Documents ───────────────────────────────────────────────────────


class TestUploadDocument(ServiceTestBase):

    def test_upload_success(self):
        booking = create_booking(self.customer, self.user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile('invoice.pdf', b'%PDF content', content_type='application/pdf')
        data = {'document_type': 'COMMERCIAL_INVOICE', 'notes': 'Test'}
        form = BookingDocumentForm(data, {'file': file})
        doc = BookingService.upload_document(booking, form, self.user)
        self.assertEqual(doc.document_type, 'COMMERCIAL_INVOICE')
        self.assertEqual(doc.uploaded_by, self.user)
        self.assertEqual(doc.original_filename, 'invoice.pdf')

    def test_upload_on_completed_raises(self):
        booking = create_booking(self.customer, self.user, status='COMPLETED')
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile('doc.pdf', b'%PDF', content_type='application/pdf')
        form = BookingDocumentForm({'document_type': 'OTHER', 'notes': ''}, {'file': file})
        with self.assertRaises(ValueError):
            BookingService.upload_document(booking, form, self.user)

    def test_upload_creates_audit_log(self):
        booking = create_booking(self.customer, self.user)
        from django.core.files.uploadedfile import SimpleUploadedFile
        file = SimpleUploadedFile('test.pdf', b'%PDF', content_type='application/pdf')
        form = BookingDocumentForm({'document_type': 'OTHER', 'notes': ''}, {'file': file})
        BookingService.upload_document(booking, form, self.user)
        log = AuditLog.objects.filter(booking=booking, action='DOCUMENT_UPLOADED').first()
        self.assertIsNotNone(log)


class TestDeleteDocument(ServiceTestBase):

    def test_delete_on_draft(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user)
        doc_id = doc.id
        BookingService.delete_document(booking, doc, self.user)
        self.assertFalse(BookingDocument.objects.filter(id=doc_id).exists())

    def test_delete_on_non_draft_raises(self):
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        doc = create_document(booking, self.user)
        with self.assertRaises(ValueError):
            BookingService.delete_document(booking, doc, self.user)

    def test_delete_creates_audit_log(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user)
        BookingService.delete_document(booking, doc, self.user)
        log = AuditLog.objects.filter(booking=booking, action='DOCUMENT_DELETED').first()
        self.assertIsNotNone(log)


# ─── Parties ─────────────────────────────────────────────────────────


class TestAddPartyToBooking(ServiceTestBase):

    def test_add_party_success(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, role='SHIPPER')
        bp = BookingService.add_party_to_booking(booking, party)
        self.assertEqual(bp.role, 'SHIPPER')
        self.assertEqual(bp.company_name, party.company_name)

    def test_add_party_with_role_override(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, role='SHIPPER')
        bp = BookingService.add_party_to_booking(booking, party, role='CONSIGNEE')
        self.assertEqual(bp.role, 'CONSIGNEE')

    def test_add_party_on_completed_raises(self):
        booking = create_booking(self.customer, self.user, status='COMPLETED')
        party = create_party(self.customer)
        with self.assertRaises(ValueError):
            BookingService.add_party_to_booking(booking, party)

    def test_add_party_creates_audit_log(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer)
        BookingService.add_party_to_booking(booking, party, user=self.user)
        log = AuditLog.objects.filter(booking=booking, action='PARTY_ADDED').first()
        self.assertIsNotNone(log)


class TestRemovePartyFromBooking(ServiceTestBase):

    def test_remove_party_success(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer)
        bp = BookingService.add_party_to_booking(booking, party)
        bp_id = bp.id
        BookingService.remove_party_from_booking(booking, bp, user=self.user)
        self.assertFalse(BookingParty.objects.filter(id=bp_id).exists())

    def test_remove_party_on_completed_raises(self):
        booking = create_booking(self.customer, self.user, status='COMPLETED')
        # Create the party manually since add would also raise
        party = create_party(self.customer)
        bp = BookingParty.create_from_party(booking, party)
        with self.assertRaises(ValueError):
            BookingService.remove_party_from_booking(booking, bp)

    def test_remove_party_creates_audit_log(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer)
        bp = BookingService.add_party_to_booking(booking, party)
        BookingService.remove_party_from_booking(booking, bp, user=self.user)
        log = AuditLog.objects.filter(booking=booking, action='PARTY_REMOVED').first()
        self.assertIsNotNone(log)


# ─── Audit helpers ───────────────────────────────────────────────────


class TestAuditHelpers(ServiceTestBase):

    def test_log_captures_ip_and_user_agent(self):
        booking = create_booking(self.customer, self.user)
        request = self._make_request()
        BookingService._log(booking, 'CREATED', user=self.user, request=request)
        log = AuditLog.objects.filter(booking=booking).first()
        self.assertEqual(log.ip_address, '127.0.0.1')
        self.assertEqual(log.user_agent, 'TestBrowser/1.0')

    def test_booking_snapshot_keys(self):
        booking = create_booking(self.customer, self.user)
        snap = BookingService._booking_snapshot(booking)
        expected_keys = {
            'status', 'transport_mode', 'origin_port', 'destination_port',
            'cargo_ready_date', 'container_type', 'container_count',
            'incoterms', 'incoterms_location', 'commodity_description',
            'is_hazardous', 'special_instructions', 'external_reference',
            'chargeable_weight_kg', 'flight_number',
        }
        self.assertEqual(set(snap.keys()), expected_keys)

    def test_log_without_request(self):
        booking = create_booking(self.customer, self.user)
        BookingService._log(booking, 'CREATED', user=self.user)
        log = AuditLog.objects.filter(booking=booking).first()
        self.assertIsNone(log.ip_address)
        self.assertEqual(log.user_agent, '')


# ─── Cancel policy (confirmed bookings) ─────────────────────────────


class TestCancelPolicy(ServiceTestBase):
    """Tests for the confirmed-booking cancel policy."""

    def test_cancel_confirmed_by_customer_fails(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        with self.assertRaises(ValueError) as ctx:
            BookingService.cancel_booking(
                booking, user=self.user, reason='Customer wants cancel',
            )
        self.assertIn('staff', str(ctx.exception).lower())

    def test_cancel_confirmed_by_staff_without_reason_fails(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        with self.assertRaises(ValueError) as ctx:
            BookingService.cancel_booking(booking, user=self.staff, reason='')
        self.assertIn('reason', str(ctx.exception).lower())

    def test_cancel_confirmed_by_staff_with_reason_succeeds(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        BookingService.cancel_booking(
            booking, user=self.staff, reason='Customer requested',
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(booking.cancellation_reason, 'Customer requested')

    def test_cancel_confirmed_with_null_reason_fails(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        with self.assertRaises(ValueError):
            BookingService.cancel_booking(
                booking, user=self.staff, reason=None,
            )

    def test_cancel_confirmed_whitespace_reason_fails(self):
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        with self.assertRaises(ValueError):
            BookingService.cancel_booking(
                booking, user=self.staff, reason='   ',
            )


# ─── Submit guard (FCL container check) ─────────────────────────────


class TestSubmitGuard(ServiceTestBase):
    """Tests for the FCL container requirement on submit."""

    def test_submit_fcl_without_container_type_fails(self):
        booking = create_booking(
            self.customer, self.user,
            transport_mode='SEA_FCL', container_type=None, container_count=2,
        )
        create_booking_item(booking)
        with self.assertRaises(ValueError) as ctx:
            BookingService.submit_booking(booking, self.user)
        self.assertIn('container', str(ctx.exception).lower())

    def test_submit_fcl_without_container_count_fails(self):
        booking = create_booking(
            self.customer, self.user,
            transport_mode='SEA_FCL', container_count=None,
        )
        create_booking_item(booking)
        with self.assertRaises(ValueError) as ctx:
            BookingService.submit_booking(booking, self.user)
        self.assertIn('container', str(ctx.exception).lower())

    def test_submit_air_without_container_succeeds(self):
        booking = create_booking(
            self.customer, self.user,
            transport_mode='AIR', container_type=None, container_count=None,
        )
        create_booking_item(booking)
        BookingService.submit_booking(booking, self.user)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'SUBMITTED')


# ─── Dict-based create (API/EDI channels) ───────────────────────────


class TestCreateBookingFromData(ServiceTestBase):
    """Tests for BookingService.create_booking_from_data."""

    def _data(self, **overrides):
        data = {
            'transport_mode': 'SEA_FCL',
            'origin_port': self.port_origin,
            'destination_port': self.port_dest,
            'cargo_ready_date': date.today() + timedelta(days=14),
            'container_type': self.container_type,
            'container_count': 2,
            'incoterms': 'FOB',
        }
        data.update(overrides)
        return data

    def _items(self):
        return [
            {
                'description': 'Test cargo',
                'quantity': 10,
                'weight_kg': Decimal('500.00'),
                'package_type': 'CARTON',
            },
        ]

    def test_create_from_data_success(self):
        booking = BookingService.create_booking_from_data(
            data=self._data(), items_data=self._items(),
            customer=self.customer, user=self.user,
        )
        self.assertEqual(booking.status, 'DRAFT')
        self.assertEqual(booking.customer, self.customer)
        self.assertEqual(booking.items.count(), 1)

    def test_create_from_data_with_parties(self):
        parties = [
            {'role': 'SHIPPER', 'company_name': 'Shipper Co'},
            {'role': 'CONSIGNEE', 'company_name': 'Consignee Co'},
        ]
        booking = BookingService.create_booking_from_data(
            data=self._data(), items_data=self._items(),
            customer=self.customer, user=self.user,
            parties_data=parties,
        )
        self.assertEqual(booking.booking_parties.count(), 2)
        roles = set(booking.booking_parties.values_list('role', flat=True))
        self.assertEqual(roles, {'SHIPPER', 'CONSIGNEE'})

    def test_create_from_data_source_channel(self):
        booking = BookingService.create_booking_from_data(
            data=self._data(), items_data=self._items(),
            customer=self.customer, user=self.user,
            source_channel='EDI',
        )
        self.assertEqual(booking.source_channel, 'EDI')

    def test_create_from_data_generates_booking_number(self):
        booking = BookingService.create_booking_from_data(
            data=self._data(), items_data=self._items(),
            customer=self.customer, user=self.user,
        )
        self.assertTrue(booking.booking_number.startswith('BK-'))

    def test_create_from_data_recalculates_totals(self):
        booking = BookingService.create_booking_from_data(
            data=self._data(), items_data=self._items(),
            customer=self.customer, user=self.user,
        )
        self.assertEqual(booking.total_weight_kg, Decimal('500.00'))


# ─── Dict-based update (API channel) ────────────────────────────────


class TestUpdateBookingFromData(ServiceTestBase):
    """Tests for BookingService.update_booking_from_data."""

    def _create_draft(self):
        return BookingService.create_booking_from_data(
            data={
                'transport_mode': 'SEA_FCL',
                'origin_port': self.port_origin,
                'destination_port': self.port_dest,
                'cargo_ready_date': date.today() + timedelta(days=14),
                'container_type': self.container_type,
                'container_count': 2,
                'incoterms': 'FOB',
            },
            items_data=[{
                'description': 'Original cargo',
                'quantity': 5,
                'weight_kg': Decimal('200.00'),
                'package_type': 'CARTON',
            }],
            customer=self.customer,
            user=self.user,
        )

    def test_update_from_data_changes_fields(self):
        booking = self._create_draft()
        updated = BookingService.update_booking_from_data(
            booking,
            data={'commodity_description': 'Updated description'},
            user=self.user,
        )
        self.assertEqual(updated.commodity_description, 'Updated description')

    def test_update_from_data_replaces_items(self):
        booking = self._create_draft()
        self.assertEqual(booking.items.count(), 1)
        new_items = [
            {'description': 'New A', 'quantity': 3, 'weight_kg': Decimal('100.00')},
            {'description': 'New B', 'quantity': 7, 'weight_kg': Decimal('300.00')},
        ]
        updated = BookingService.update_booking_from_data(
            booking, data={}, user=self.user, items_data=new_items,
        )
        self.assertEqual(updated.items.count(), 2)
        self.assertEqual(updated.total_weight_kg, Decimal('400.00'))

    def test_update_from_data_non_draft_fails(self):
        booking = self._create_draft()
        booking.status = 'SUBMITTED'
        booking.save()
        with self.assertRaises(ValueError):
            BookingService.update_booking_from_data(
                booking, data={'commodity_description': 'Fail'}, user=self.user,
            )

    def test_update_from_data_partial_update(self):
        booking = self._create_draft()
        original_mode = booking.transport_mode
        BookingService.update_booking_from_data(
            booking,
            data={'special_instructions': 'Handle carefully'},
            user=self.user,
        )
        booking.refresh_from_db()
        self.assertEqual(booking.special_instructions, 'Handle carefully')
        self.assertEqual(booking.transport_mode, original_mode)
