"""
Tests for bookings.models — model behavior, status transitions, computed properties.

Uses TestCase (needs database).
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from bookings.models import (
    Customer, Booking, BookingItem, BookingDocument, BookingParty, Party, AuditLog,
    ShipmentMilestone,
)
from bookings.tests.helpers import (
    create_customer, create_user, create_port, create_container_type,
    create_booking, create_booking_item, create_party, create_document,
    create_milestone,
)


class TestCustomerModel(TestCase):

    def test_str(self):
        c = create_customer(code='ACME', name='Acme Corp')
        self.assertEqual(str(c), 'ACME - Acme Corp')

    def test_ordering_by_name(self):
        create_customer(code='ZZZ', name='Zeta Inc')
        create_customer(code='AAA', name='Alpha Corp')
        names = list(Customer.objects.values_list('name', flat=True))
        self.assertEqual(names, ['Alpha Corp', 'Zeta Inc'])


class TestBookingModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)
        cls.staff = create_user(username='staff', is_staff=True)
        cls.port_origin = create_port()
        cls.port_dest = create_port(code='CNSHA', name='Shanghai', country='CN')
        cls.container_type = create_container_type()

    def _create_booking(self, **kwargs):
        return create_booking(self.customer, self.user, **kwargs)

    # ─── Booking number generation ──────────────────────────────────

    def test_booking_number_auto_generated(self):
        booking = self._create_booking()
        self.assertTrue(booking.booking_number.startswith('BK-'))
        self.assertEqual(len(booking.booking_number), 14)  # BK-YYYYMM-NNNN

    def test_booking_number_unique(self):
        b1 = self._create_booking()
        b2 = self._create_booking()
        self.assertNotEqual(b1.booking_number, b2.booking_number)

    def test_booking_number_sequential(self):
        b1 = self._create_booking()
        b2 = self._create_booking()
        num1 = int(b1.booking_number.split('-')[-1])
        num2 = int(b2.booking_number.split('-')[-1])
        self.assertEqual(num2, num1 + 1)

    def test_booking_number_not_overwritten_on_save(self):
        booking = self._create_booking()
        original_number = booking.booking_number
        booking.special_instructions = 'Updated'
        booking.save()
        self.assertEqual(booking.booking_number, original_number)

    # ─── Defaults ───────────────────────────────────────────────────

    def test_default_status_draft(self):
        booking = self._create_booking()
        self.assertEqual(booking.status, 'DRAFT')

    def test_default_container_count(self):
        booking = self._create_booking()
        self.assertEqual(booking.container_count, 1)

    def test_default_transport_mode(self):
        booking = self._create_booking()
        self.assertEqual(booking.transport_mode, 'SEA_FCL')

    def test_str(self):
        booking = self._create_booking()
        self.assertIn(booking.booking_number, str(booking))
        self.assertIn('DRAFT', str(booking))

    # ─── recalculate_totals ─────────────────────────────────────────

    def test_recalculate_totals_weight(self):
        booking = self._create_booking()
        create_booking_item(booking, weight_kg=Decimal('100.00'))
        create_booking_item(booking, description='Item 2', weight_kg=Decimal('200.50'))
        booking.recalculate_totals()
        self.assertEqual(booking.total_weight_kg, Decimal('300.50'))

    def test_recalculate_totals_volume(self):
        booking = self._create_booking()
        create_booking_item(booking, volume_cbm=Decimal('1.500'))
        create_booking_item(booking, description='Item 2', volume_cbm=Decimal('2.500'))
        booking.recalculate_totals()
        self.assertEqual(booking.total_volume_cbm, Decimal('4.000'))

    def test_recalculate_totals_no_items(self):
        booking = self._create_booking()
        booking.recalculate_totals()
        self.assertEqual(booking.total_weight_kg, Decimal('0.00'))
        self.assertEqual(booking.total_volume_cbm, Decimal('0.000'))

    # ─── Status transitions ─────────────────────────────────────────

    def test_submit_from_draft(self):
        booking = self._create_booking()
        create_booking_item(booking)
        booking.submit()
        self.assertEqual(booking.status, 'SUBMITTED')
        self.assertIsNotNone(booking.submitted_at)

    def test_submit_requires_items(self):
        booking = self._create_booking()
        with self.assertRaises(ValueError):
            booking.submit()

    def test_submit_from_non_draft_ignored(self):
        booking = self._create_booking(status='SUBMITTED')
        create_booking_item(booking)
        # submit() silently returns when not DRAFT (model-level behavior)
        booking.submit()
        self.assertEqual(booking.status, 'SUBMITTED')

    def test_confirm_from_submitted(self):
        booking = self._create_booking(status='SUBMITTED')
        booking.confirm(user=self.staff)
        self.assertEqual(booking.status, 'CONFIRMED')
        self.assertIsNotNone(booking.confirmed_at)
        self.assertEqual(booking.confirmed_by, self.staff)

    def test_confirm_from_non_submitted_raises(self):
        booking = self._create_booking(status='DRAFT')
        with self.assertRaises(ValueError):
            booking.confirm()

    def test_reject_from_submitted(self):
        booking = self._create_booking(status='SUBMITTED')
        booking.reject(user=self.staff, reason='Incomplete docs')
        self.assertEqual(booking.status, 'REJECTED')
        self.assertIsNotNone(booking.rejected_at)
        self.assertEqual(booking.rejected_by, self.staff)
        self.assertEqual(booking.rejection_reason, 'Incomplete docs')

    def test_reject_from_non_submitted_raises(self):
        booking = self._create_booking(status='DRAFT')
        with self.assertRaises(ValueError):
            booking.reject()

    def test_mark_in_transit_from_confirmed(self):
        booking = self._create_booking(status='CONFIRMED')
        booking.mark_in_transit()
        self.assertEqual(booking.status, 'IN_TRANSIT')
        self.assertIsNotNone(booking.in_transit_at)

    def test_mark_in_transit_from_non_confirmed_raises(self):
        booking = self._create_booking(status='SUBMITTED')
        with self.assertRaises(ValueError):
            booking.mark_in_transit()

    def test_complete_from_in_transit(self):
        booking = self._create_booking(status='IN_TRANSIT')
        booking.complete()
        self.assertEqual(booking.status, 'COMPLETED')
        self.assertIsNotNone(booking.completed_at)

    def test_complete_from_non_in_transit_raises(self):
        booking = self._create_booking(status='CONFIRMED')
        with self.assertRaises(ValueError):
            booking.complete()

    def test_cancel_from_draft(self):
        booking = self._create_booking(status='DRAFT')
        booking.cancel(user=self.user, reason='Changed mind')
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertIsNotNone(booking.cancelled_at)
        self.assertEqual(booking.cancelled_by, self.user)
        self.assertEqual(booking.cancellation_reason, 'Changed mind')

    def test_cancel_from_submitted(self):
        booking = self._create_booking(status='SUBMITTED')
        booking.cancel()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_from_confirmed(self):
        booking = self._create_booking(status='CONFIRMED')
        booking.cancel()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_from_in_transit_raises(self):
        booking = self._create_booking(status='IN_TRANSIT')
        with self.assertRaises(ValueError):
            booking.cancel()

    def test_cancel_from_completed_raises(self):
        booking = self._create_booking(status='COMPLETED')
        with self.assertRaises(ValueError):
            booking.cancel()

    # ─── ARRIVED status transitions ──────────────────────────────────

    def test_mark_arrived_from_in_transit(self):
        booking = self._create_booking(status='IN_TRANSIT')
        booking.mark_arrived()
        self.assertEqual(booking.status, 'ARRIVED')
        self.assertIsNotNone(booking.arrived_at)

    def test_mark_arrived_from_non_in_transit_raises(self):
        booking = self._create_booking(status='CONFIRMED')
        with self.assertRaises(ValueError):
            booking.mark_arrived()

    def test_complete_from_arrived(self):
        booking = self._create_booking(status='ARRIVED')
        booking.complete()
        self.assertEqual(booking.status, 'COMPLETED')
        self.assertIsNotNone(booking.completed_at)

    def test_complete_from_in_transit_still_works(self):
        booking = self._create_booking(status='IN_TRANSIT')
        booking.complete()
        self.assertEqual(booking.status, 'COMPLETED')

    def test_cancel_from_arrived_raises(self):
        booking = self._create_booking(status='ARRIVED')
        with self.assertRaises(ValueError):
            booking.cancel()


class TestShipmentMilestoneModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)

    def test_milestone_str(self):
        booking = create_booking(self.customer, self.user)
        ms = create_milestone(booking, milestone_type='CARGO_RECEIVED')
        self.assertIn(booking.booking_number, str(ms))
        self.assertIn('Cargo Received', str(ms))

    def test_milestone_ordering_by_occurred_at(self):
        booking = create_booking(self.customer, self.user)
        from django.utils import timezone
        from datetime import timedelta
        t1 = timezone.now() - timedelta(hours=2)
        t2 = timezone.now()
        ms2 = create_milestone(booking, milestone_type='DEPARTED', occurred_at=t2)
        ms1 = create_milestone(booking, milestone_type='GATE_IN', occurred_at=t1)
        milestones = list(booking.milestones.values_list('milestone_type', flat=True))
        self.assertEqual(milestones, ['GATE_IN', 'DEPARTED'])


class TestBookingItemModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)

    def test_str(self):
        booking = create_booking(self.customer, self.user)
        item = create_booking_item(booking, description='Monitors', quantity=5, weight_kg=Decimal('50.00'))
        self.assertEqual(str(item), '5x Monitors (50.00kg)')

    def test_calculated_volume_with_dimensions(self):
        booking = create_booking(self.customer, self.user)
        item = create_booking_item(
            booking,
            length_cm=Decimal('100.00'),
            width_cm=Decimal('50.00'),
            height_cm=Decimal('30.00'),
        )
        expected = Decimal('100.00') * Decimal('50.00') * Decimal('30.00') / 1_000_000
        self.assertEqual(item.calculated_volume_cbm, expected)

    def test_calculated_volume_without_dimensions_returns_volume_cbm(self):
        booking = create_booking(self.customer, self.user)
        item = create_booking_item(booking, volume_cbm=Decimal('2.500'))
        self.assertEqual(item.calculated_volume_cbm, Decimal('2.500'))

    def test_calculated_volume_no_dims_no_volume(self):
        booking = create_booking(self.customer, self.user)
        item = create_booking_item(booking)
        self.assertIsNone(item.calculated_volume_cbm)

    def test_meta_verbose_name(self):
        self.assertEqual(BookingItem._meta.verbose_name, 'cargo line item')
        self.assertEqual(BookingItem._meta.verbose_name_plural, 'cargo line items')


class TestBookingDocumentModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)

    def test_file_size_display_bytes(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user, file_size=500)
        self.assertEqual(doc.file_size_display, '500 B')

    def test_file_size_display_kb(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user, file_size=2048)
        self.assertEqual(doc.file_size_display, '2.0 KB')

    def test_file_size_display_mb(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user, file_size=2 * 1024 * 1024)
        self.assertEqual(doc.file_size_display, '2.0 MB')

    def test_file_extension(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user, filename='invoice.pdf')
        self.assertEqual(doc.file_extension, '.pdf')

    def test_str(self):
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user, doc_type='COMMERCIAL_INVOICE', filename='inv.pdf')
        self.assertIn('Commercial Invoice', str(doc))


class TestBookingPartyModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.user = create_user(customer=cls.customer)

    def test_create_from_party(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(
            self.customer,
            role='SHIPPER',
            company_name='Export Co',
            contact_name='Jane',
            email='jane@export.com',
            phone='+1-555-9999',
        )
        bp = BookingParty.create_from_party(booking, party)
        self.assertEqual(bp.role, 'SHIPPER')
        self.assertEqual(bp.company_name, 'Export Co')
        self.assertEqual(bp.contact_name, 'Jane')
        self.assertEqual(bp.email, 'jane@export.com')
        self.assertEqual(bp.phone, '+1-555-9999')
        self.assertEqual(bp.party, party)
        self.assertEqual(bp.address_text, party.full_address)

    def test_create_from_party_with_role_override(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, role='SHIPPER')
        bp = BookingParty.create_from_party(booking, party, role='CONSIGNEE')
        self.assertEqual(bp.role, 'CONSIGNEE')

    def test_unique_role_per_booking(self):
        booking = create_booking(self.customer, self.user)
        party1 = create_party(self.customer, role='SHIPPER', company_name='Shipper A')
        party2 = create_party(self.customer, role='CONSIGNEE', company_name='Consignee B')
        BookingParty.create_from_party(booking, party1, role='SHIPPER')
        # Same role on same booking should fail
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            BookingParty.create_from_party(booking, party2, role='SHIPPER')

    def test_str(self):
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, company_name='Test Shipper Co')
        bp = BookingParty.create_from_party(booking, party)
        self.assertIn('Test Shipper Co', str(bp))


class TestPartyModel(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()

    def test_full_address(self):
        party = create_party(
            self.customer,
            address_line_1='123 Main St',
            city='New York',
            state='NY',
            postal_code='10001',
            country_code='US',
        )
        addr = party.full_address
        self.assertIn('123 Main St', addr)
        self.assertIn('New York', addr)
        self.assertIn('NY', addr)
        self.assertIn('10001', addr)
        self.assertIn('US', addr)

    def test_full_address_empty_parts_excluded(self):
        party = create_party(self.customer, address_line_1='', city='Shanghai', country_code='CN')
        addr = party.full_address
        self.assertNotIn(', ,', addr)  # no double commas from empty parts

    def test_str(self):
        party = create_party(self.customer, company_name='Acme', role='CONSIGNEE')
        self.assertIn('Acme', str(party))
        self.assertIn('Consignee', str(party))

    def test_default_auto_replaces_existing(self):
        """Setting a new default should auto-clear the previous default."""
        p1 = create_party(self.customer, company_name='First', role='SHIPPER', is_default=True)
        p2 = create_party(self.customer, company_name='Second', role='SHIPPER', is_default=True)
        p1.refresh_from_db()
        self.assertFalse(p1.is_default)
        self.assertTrue(p2.is_default)

    def test_default_different_roles_coexist(self):
        """Different roles can each have their own default."""
        p1 = create_party(self.customer, company_name='Shipper', role='SHIPPER', is_default=True)
        p2 = create_party(self.customer, company_name='Consignee', role='CONSIGNEE', is_default=True)
        p1.refresh_from_db()
        self.assertTrue(p1.is_default)
        self.assertTrue(p2.is_default)

    def test_default_different_customers_coexist(self):
        """Same role defaults on different customers don't interfere."""
        other = create_customer(code='OTHER', name='Other Customer')
        p1 = create_party(self.customer, role='SHIPPER', is_default=True)
        p2 = create_party(other, role='SHIPPER', is_default=True)
        p1.refresh_from_db()
        self.assertTrue(p1.is_default)
        self.assertTrue(p2.is_default)

    def test_resaving_existing_default_keeps_it(self):
        """Re-saving the existing default party should not clear itself."""
        p1 = create_party(self.customer, role='SHIPPER', is_default=True)
        p1.save()  # re-save
        p1.refresh_from_db()
        self.assertTrue(p1.is_default)
