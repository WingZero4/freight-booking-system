"""
Tests for bookings.views — all 24 views.

Uses TestCase + self.client for HTTP-level integration tests.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile

from bookings.models import Booking, BookingItem, BookingParty, BookingDocument, AuditLog
from bookings.tests.helpers import (
    create_customer, create_user, create_port, create_container_type,
    create_booking, create_booking_item, create_party, create_document,
)


class ViewTestBase(TestCase):
    """Shared setup for all view tests."""

    @classmethod
    def setUpTestData(cls):
        cls.customer = create_customer()
        cls.customer2 = create_customer(code='CUST02', name='Other Customer')
        cls.user = create_user(username='custuser', customer=cls.customer)
        cls.user2 = create_user(username='custuser2', customer=cls.customer2)
        cls.staff = create_user(username='staffuser', is_staff=True)
        cls.port_origin = create_port()
        cls.port_dest = create_port(code='CNSHA', name='Shanghai', country='CN')
        cls.container_type = create_container_type()

    def _login_customer(self):
        self.client.login(username='custuser', password='testpass123')

    def _login_customer2(self):
        self.client.login(username='custuser2', password='testpass123')

    def _login_staff(self):
        self.client.login(username='staffuser', password='testpass123')

    def _booking_post_data(self, **overrides):
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
            'is_hazardous': '',
            'external_reference': 'TEST-REF-001',
            'special_instructions': '',
            # formset management
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-description': 'Monitors',
            'items-0-package_type': 'CARTON',
            'items-0-quantity': '10',
            'items-0-weight_kg': '100.00',
            'items-0-hs_code': '',
            'items-0-volume_cbm': '',
            'items-0-length_cm': '',
            'items-0-width_cm': '',
            'items-0-height_cm': '',
            'items-0-marks_and_numbers': '',
            'items-0-is_hazardous': '',
            'items-0-un_number': '',
            'items-0-imo_class': '',
            'items-0-country_of_origin': '',
        }
        data.update(overrides)
        return data


# ─── Authentication ──────────────────────────────────────────────────


class TestAuthRequired(ViewTestBase):

    def test_dashboard_requires_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_booking_list_requires_login(self):
        resp = self.client.get(reverse('booking_list'))
        self.assertEqual(resp.status_code, 302)

    def test_booking_create_requires_login(self):
        resp = self.client.get(reverse('booking_create'))
        self.assertEqual(resp.status_code, 302)

    def test_ops_dashboard_requires_login(self):
        resp = self.client.get(reverse('ops_dashboard'))
        self.assertEqual(resp.status_code, 302)


# ─── Dashboard ───────────────────────────────────────────────────────


class TestDashboard(ViewTestBase):

    def test_customer_sees_dashboard(self):
        self._login_customer()
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('stats', resp.context)

    def test_staff_sees_ops_dashboard(self):
        self._login_staff()
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Operations Dashboard')


# ─── Booking list ────────────────────────────────────────────────────


class TestBookingList(ViewTestBase):

    def test_customer_sees_own_bookings(self):
        self._login_customer()
        create_booking(self.customer, self.user)
        create_booking(self.customer2, self.user2)  # other customer
        resp = self.client.get(reverse('booking_list'))
        self.assertEqual(resp.status_code, 200)
        bookings = resp.context['page_obj'].object_list
        for b in bookings:
            self.assertEqual(b.customer, self.customer)

    def test_staff_sees_all_bookings(self):
        self._login_staff()
        create_booking(self.customer, self.user)
        create_booking(self.customer2, self.user2)
        resp = self.client.get(reverse('booking_list'))
        self.assertEqual(len(resp.context['page_obj'].object_list), 2)

    def test_status_filter(self):
        self._login_customer()
        create_booking(self.customer, self.user, status='DRAFT')
        create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('booking_list'), {'status': 'DRAFT'})
        for b in resp.context['page_obj'].object_list:
            self.assertEqual(b.status, 'DRAFT')

    def test_search_filter(self):
        self._login_customer()
        b = create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_list'), {'q': b.booking_number[:6]})
        self.assertIn(b, resp.context['page_obj'].object_list)

    def test_date_range_filter(self):
        self._login_customer()
        create_booking(self.customer, self.user)
        today = date.today().isoformat()
        resp = self.client.get(reverse('booking_list'), {
            'date_from': today,
            'date_to': today,
        })
        self.assertEqual(resp.status_code, 200)

    def test_sort(self):
        self._login_customer()
        resp = self.client.get(reverse('booking_list'), {'sort': 'booking_number'})
        self.assertEqual(resp.status_code, 200)

    def test_pagination(self):
        self._login_customer()
        for _ in range(15):
            create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_list'))
        self.assertTrue(resp.context['page_obj'].has_next())


# ─── Booking CRUD ────────────────────────────────────────────────────


class TestBookingCreate(ViewTestBase):

    def test_get_form(self):
        self._login_customer()
        resp = self.client.get(reverse('booking_create'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('form', resp.context)
        self.assertIn('formset', resp.context)

    def test_post_creates_booking(self):
        self._login_customer()
        resp = self.client.post(reverse('booking_create'), self._booking_post_data())
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Booking.objects.filter(customer=self.customer).count(), 1)

    def test_post_invalid_form_shows_errors(self):
        self._login_customer()
        data = self._booking_post_data(origin_port='')
        resp = self.client.post(reverse('booking_create'), data)
        self.assertEqual(resp.status_code, 200)  # re-renders form
        self.assertTrue(resp.context['form'].errors)

    def test_staff_can_create_with_customer_selector(self):
        self._login_staff()
        resp = self.client.get(reverse('booking_create'))
        # Staff sees the booking form with customer selector
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['is_staff_create'])


class TestBookingEdit(ViewTestBase):

    def test_edit_draft_get(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        resp = self.client.get(reverse('booking_edit', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)

    def test_edit_submitted_allowed(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('booking_edit', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)

    def test_edit_confirmed_redirects(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.get(reverse('booking_edit', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))

    def test_edit_other_customer_404(self):
        self._login_customer2()
        booking = create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_edit', args=[booking.id]))
        self.assertEqual(resp.status_code, 404)


class TestBookingDetail(ViewTestBase):

    def test_detail_view(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        resp = self.client.get(reverse('booking_detail', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['booking'], booking)

    def test_other_customer_404(self):
        self._login_customer2()
        booking = create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_detail', args=[booking.id]))
        self.assertEqual(resp.status_code, 404)

    def test_staff_sees_any_booking(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_detail', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)

    def test_nonexistent_booking_404(self):
        self._login_customer()
        resp = self.client.get(reverse('booking_detail', args=[99999]))
        self.assertEqual(resp.status_code, 404)


# ─── Status transitions ─────────────────────────────────────────────


class TestBookingSubmit(ViewTestBase):

    def test_submit_get_shows_confirmation(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        resp = self.client.get(reverse('booking_submit', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)

    def test_submit_post_changes_status(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        create_booking_item(booking)
        resp = self.client.post(reverse('booking_submit', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'SUBMITTED')
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))

    def test_submit_non_draft_redirects(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('booking_submit', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


class TestBookingCancel(ViewTestBase):

    def test_cancel_draft_post(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        resp = self.client.post(reverse('booking_cancel', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')

    def test_cancel_confirmed_requires_reason(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.post(
            reverse('booking_cancel', args=[booking.id]),
            {'reason': 'Customer requested cancellation'},
        )
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(booking.cancellation_reason, 'Customer requested cancellation')

    def test_customer_cannot_cancel_confirmed(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.post(reverse('booking_cancel', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CONFIRMED')  # unchanged


class TestBookingResubmit(ViewTestBase):

    def test_resubmit_rejected(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='REJECTED')
        resp = self.client.post(reverse('booking_resubmit', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'DRAFT')

    def test_resubmit_non_rejected_redirects(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='DRAFT')
        resp = self.client.post(reverse('booking_resubmit', args=[booking.id]))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'DRAFT')  # unchanged


# ─── Documents ───────────────────────────────────────────────────────


class TestDocumentUpload(ViewTestBase):

    def test_upload_success(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        file = SimpleUploadedFile('invoice.pdf', b'%PDF-1.4 content', content_type='application/pdf')
        resp = self.client.post(
            reverse('booking_document_upload', args=[booking.id]),
            {'document_type': 'COMMERCIAL_INVOICE', 'file': file, 'notes': ''},
        )
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        self.assertEqual(booking.documents.count(), 1)

    def test_upload_blocked_on_completed(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='COMPLETED')
        file = SimpleUploadedFile('doc.pdf', b'%PDF', content_type='application/pdf')
        self.client.post(
            reverse('booking_document_upload', args=[booking.id]),
            {'document_type': 'OTHER', 'file': file, 'notes': ''},
        )
        self.assertEqual(booking.documents.count(), 0)


class TestDocumentDelete(ViewTestBase):

    def test_delete_on_draft(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        doc = create_document(booking, self.user)
        resp = self.client.post(
            reverse('booking_document_delete', args=[booking.id, doc.id])
        )
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        self.assertEqual(booking.documents.count(), 0)

    def test_delete_on_submitted_blocked(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        doc = create_document(booking, self.user)
        resp = self.client.post(
            reverse('booking_document_delete', args=[booking.id, doc.id])
        )
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        self.assertEqual(booking.documents.count(), 1)  # document not deleted


# ─── Parties ─────────────────────────────────────────────────────────


class TestPartyViews(ViewTestBase):

    def test_party_list(self):
        self._login_customer()
        create_party(self.customer, company_name='Test Co')
        resp = self.client.get(reverse('party_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['page_obj'].object_list), 1)

    def test_party_create(self):
        self._login_customer()
        resp = self.client.post(reverse('party_create'), {
            'role': 'CONSIGNEE',
            'company_name': 'Import Co',
            'contact_name': 'Jane',
            'email': 'jane@import.com',
            'phone': '',
            'address_line_1': '', 'address_line_2': '',
            'city': '', 'state': '', 'postal_code': '',
            'country_code': '', 'tax_id': '',
            'is_default': '',
        })
        self.assertRedirects(resp, reverse('party_list'))
        from bookings.models import Party
        self.assertTrue(Party.objects.filter(company_name='Import Co').exists())

    def test_party_edit(self):
        self._login_customer()
        party = create_party(self.customer, company_name='Old Name')
        resp = self.client.post(reverse('party_edit', args=[party.id]), {
            'role': 'SHIPPER',
            'company_name': 'New Name',
            'contact_name': '', 'email': '', 'phone': '',
            'address_line_1': '', 'address_line_2': '',
            'city': '', 'state': '', 'postal_code': '',
            'country_code': '', 'tax_id': '',
            'is_default': '',
        })
        party.refresh_from_db()
        self.assertEqual(party.company_name, 'New Name')

    def test_party_delete_deactivates(self):
        self._login_customer()
        party = create_party(self.customer)
        self.client.post(reverse('party_delete', args=[party.id]))
        party.refresh_from_db()
        self.assertFalse(party.is_active)

    def test_other_customer_party_404(self):
        self._login_customer2()
        party = create_party(self.customer)
        resp = self.client.get(reverse('party_edit', args=[party.id]))
        self.assertEqual(resp.status_code, 404)


class TestBookingPartyAssignment(ViewTestBase):

    def test_add_party_to_booking(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, role='SHIPPER')
        resp = self.client.post(
            reverse('booking_party_add', args=[booking.id]),
            {'party': party.id, 'role': 'SHIPPER'},
        )
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        self.assertEqual(booking.booking_parties.count(), 1)

    def test_duplicate_role_rejected(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer, role='SHIPPER')
        # Add first
        self.client.post(
            reverse('booking_party_add', args=[booking.id]),
            {'party': party.id, 'role': 'SHIPPER'},
        )
        # Try adding same role again
        party2 = create_party(self.customer, role='CONSIGNEE', company_name='Second Co')
        self.client.post(
            reverse('booking_party_add', args=[booking.id]),
            {'party': party2.id, 'role': 'SHIPPER'},
        )
        self.assertEqual(booking.booking_parties.filter(role='SHIPPER').count(), 1)

    def test_remove_party_from_booking(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer)
        self.client.post(
            reverse('booking_party_add', args=[booking.id]),
            {'party': party.id, 'role': 'SHIPPER'},
        )
        bp = booking.booking_parties.first()
        self.client.post(
            reverse('booking_party_remove', args=[booking.id, bp.id])
        )
        self.assertEqual(booking.booking_parties.count(), 0)


# ─── Clone ───────────────────────────────────────────────────────────


class TestBookingClone(ViewTestBase):

    def test_clone_creates_new_draft(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        create_booking_item(booking, description='Original Cargo')
        resp = self.client.post(reverse('booking_clone', args=[booking.id]))
        self.assertEqual(resp.status_code, 302)
        new_booking = Booking.objects.exclude(id=booking.id).first()
        self.assertEqual(new_booking.status, 'DRAFT')
        self.assertEqual(new_booking.items.count(), 1)
        self.assertEqual(new_booking.items.first().description, 'Original Cargo')

    def test_clone_copies_parties(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        party = create_party(self.customer)
        BookingParty.create_from_party(booking, party, role='SHIPPER')
        self.client.post(reverse('booking_clone', args=[booking.id]))
        new_booking = Booking.objects.exclude(id=booking.id).first()
        self.assertEqual(new_booking.booking_parties.count(), 1)

    def test_staff_cannot_clone(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user)
        resp = self.client.post(reverse('booking_clone', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))
        self.assertEqual(Booking.objects.count(), 1)  # no new booking created


# ─── CSV Export ──────────────────────────────────────────────────────


class TestCSVExport(ViewTestBase):

    def test_export_csv(self):
        self._login_customer()
        create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        content = resp.content.decode()
        self.assertIn('Booking Number', content)

    def test_customer_csv_hides_contract_number(self):
        self._login_customer()
        booking = create_booking(self.customer, self.user)
        booking.contract_number = 'SECRET-123'
        booking.save()
        resp = self.client.get(reverse('booking_export_csv'))
        content = resp.content.decode()
        self.assertNotIn('Contract Number', content)
        self.assertNotIn('SECRET-123', content)

    def test_staff_csv_shows_contract_number(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user)
        booking.contract_number = 'SECRET-456'
        booking.save()
        resp = self.client.get(reverse('booking_export_csv'))
        content = resp.content.decode()
        self.assertIn('Contract Number', content)
        self.assertIn('SECRET-456', content)

    def test_csv_respects_status_filter(self):
        self._login_customer()
        create_booking(self.customer, self.user, status='DRAFT')
        create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('booking_export_csv'), {'status': 'DRAFT'})
        content = resp.content.decode()
        lines = content.strip().split('\n')
        self.assertEqual(len(lines), 2)  # header + 1 data row


# ─── Operations (Staff) ─────────────────────────────────────────────


class TestOpsAccess(ViewTestBase):

    def test_customer_cannot_access_ops(self):
        self._login_customer()
        resp = self.client.get(reverse('ops_dashboard'))
        self.assertRedirects(resp, reverse('dashboard'))

    def test_staff_can_access_ops(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_dashboard'))
        self.assertEqual(resp.status_code, 200)


class TestOpsDashboard(ViewTestBase):

    def test_dashboard_context(self):
        self._login_staff()
        create_booking(self.customer, self.user, status='SUBMITTED')
        create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.get(reverse('ops_dashboard'))
        self.assertIn('pipeline', resp.context)
        self.assertIn('pending_confirmation', resp.context)
        self.assertEqual(resp.context['pipeline']['submitted'], 1)
        self.assertEqual(resp.context['pipeline']['confirmed'], 1)


class TestOpsConfirm(ViewTestBase):

    def test_confirm_get(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('ops_booking_confirm', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('carrier_form', resp.context)

    def test_confirm_post(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.post(reverse('ops_booking_confirm', args=[booking.id]), {
            'carrier_name': 'Maersk',
            'vessel_name': 'Maersk Elba',
            'voyage_number': '',
            'cargo_cutoff_date': '',
            'etd': '',
            'eta': '',
            'carrier_booking_ref': '',
            'contract_number': '',
        })
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CONFIRMED')
        self.assertEqual(booking.carrier_name, 'Maersk')

    def test_confirm_non_submitted_redirects(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.get(reverse('ops_booking_confirm', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


class TestOpsReject(ViewTestBase):

    def test_reject_post(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.post(reverse('ops_booking_reject', args=[booking.id]), {
            'reason': 'Incomplete documentation',
        })
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'REJECTED')
        self.assertEqual(booking.rejection_reason, 'Incomplete documentation')

    def test_reject_non_submitted_redirects(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='DRAFT')
        resp = self.client.get(reverse('ops_booking_reject', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


class TestOpsCarrierDetails(ViewTestBase):

    def test_carrier_details_get(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.get(reverse('ops_carrier_details', args=[booking.id]))
        self.assertEqual(resp.status_code, 200)

    def test_carrier_details_post(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.post(reverse('ops_carrier_details', args=[booking.id]), {
            'carrier_name': 'MSC',
            'vessel_name': 'MSC Anna',
            'voyage_number': '123E',
            'cargo_cutoff_date': '',
            'etd': (date.today() + timedelta(days=5)).isoformat(),
            'eta': (date.today() + timedelta(days=25)).isoformat(),
            'carrier_booking_ref': '',
            'contract_number': '',
        })
        booking.refresh_from_db()
        self.assertEqual(booking.carrier_name, 'MSC')

    def test_carrier_details_draft_redirects(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='DRAFT')
        resp = self.client.get(reverse('ops_carrier_details', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


class TestOpsMarkInTransit(ViewTestBase):

    def test_mark_in_transit_post(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='PACKING')
        resp = self.client.post(reverse('ops_mark_in_transit', args=[booking.id]), {
            'actual_departure_date': date.today().isoformat(),
        })
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'IN_TRANSIT')
        self.assertEqual(booking.actual_departure_date, date.today())

    def test_mark_in_transit_non_packing_redirects(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='SUBMITTED')
        resp = self.client.get(reverse('ops_mark_in_transit', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


class TestOpsComplete(ViewTestBase):

    def test_complete_post(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='IN_TRANSIT')
        resp = self.client.post(reverse('ops_complete_booking', args=[booking.id]), {
            'actual_arrival_date': date.today().isoformat(),
        })
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'COMPLETED')

    def test_complete_non_in_transit_redirects(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='CONFIRMED')
        resp = self.client.get(reverse('ops_complete_booking', args=[booking.id]))
        self.assertRedirects(resp, reverse('booking_detail', args=[booking.id]))


# ─── Theme / Branding Tests ──────────────────────────────────────────────────

class ThemingTests(ViewTestBase):
    """Test the customer_theme context processor and branded templates."""

    def setUp(self):
        """Reset customer branding before each test to avoid cross-test contamination."""
        super().setUp()
        from bookings.models import Customer
        Customer.objects.filter(pk=self.customer.pk).update(
            primary_color='', accent_color='', portal_name='', logo=''
        )
        self.customer.refresh_from_db()

    def test_login_page_renders_with_default_theme(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'btn-themed-primary')
        self.assertContains(resp, 'login-card')

    def test_default_theme_for_customer_without_branding(self):
        self._login_customer()
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Freight Booking')  # default portal name
        # Default theme uses CSS file defaults, no inline override
        self.assertNotContains(resp, '#336699')

    def test_custom_theme_colors_appear(self):
        from bookings.models import Customer
        Customer.objects.filter(pk=self.customer.pk).update(
            primary_color='#336699', accent_color='#FF6600'
        )
        self._login_customer()
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, '#336699')
        self.assertContains(resp, '#FF6600')

    def test_custom_portal_name_appears(self):
        from bookings.models import Customer
        Customer.objects.filter(pk=self.customer.pk).update(
            portal_name='Acme Logistics Portal'
        )
        self._login_customer()
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'Acme Logistics Portal')

    def test_staff_sees_default_theme(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_dashboard'))
        self.assertContains(resp, 'Freight Booking')

    def test_navbar_shows_ship_icon_without_logo(self):
        self._login_customer()
        resp = self.client.get(reverse('dashboard'))
        self.assertContains(resp, 'fa-ship')
        # No <img> tag should appear in the navbar brand area
        content = resp.content.decode()
        self.assertNotIn('<img src="', content.split('navbar-brand')[1].split('</a>')[0])


# ─── Document download auth ──────────────────────────────────────────


class TestDocumentDownloadAuth(ViewTestBase):
    """Tests for authenticated document downloads."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.booking = create_booking(cls.customer, cls.user)
        create_booking_item(cls.booking)
        cls.doc = create_document(cls.booking, cls.user)

    def test_document_download_requires_login(self):
        url = reverse(
            'booking_document_download',
            args=[self.booking.id, self.doc.id],
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_document_download_customer_own_booking(self):
        self._login_customer()
        url = reverse(
            'booking_document_download',
            args=[self.booking.id, self.doc.id],
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp['Content-Disposition'],
            f'attachment; filename="{self.doc.original_filename}"',
        )

    def test_document_download_other_customer_blocked(self):
        self._login_customer2()
        url = reverse(
            'booking_document_download',
            args=[self.booking.id, self.doc.id],
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_document_download_staff_any_booking(self):
        self._login_staff()
        url = reverse(
            'booking_document_download',
            args=[self.booking.id, self.doc.id],
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)


# ── Staff Report Views ─────────────────────────────────────────────────────

class TestStaffReports(ViewTestBase):
    """Tests for staff report views."""

    def setUp(self):
        self.booking = create_booking(self.customer, self.user)

    def test_reports_hub_staff_access(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_reports_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Reports')

    def test_reports_hub_customer_denied(self):
        self._login_customer()
        resp = self.client.get(reverse('ops_reports_hub'))
        self.assertEqual(resp.status_code, 302)

    def test_overview_report(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_reports'))
        self.assertEqual(resp.status_code, 200)

    def test_volume_by_customer(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_volume_customer'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Volume by Customer')

    def test_volume_by_customer_csv(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_volume_customer'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_route_analysis(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_route'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Route Analysis')

    def test_route_analysis_csv(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_route'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_transit_performance(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_transit'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Transit Performance')

    def test_transit_performance_csv(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_transit'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_container_utilization(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_container'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Container Utilization')

    def test_carrier_performance(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_carrier'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Carrier Performance')

    def test_status_aging(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_aging'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Status Aging')

    def test_status_aging_csv(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_aging'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_date_range_preset(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_volume_customer'), {'preset': '7d'})
        self.assertEqual(resp.status_code, 200)

    def test_date_range_custom(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_report_volume_customer'), {
            'date_from': '2026-01-01', 'date_to': '2026-12-31'
        })
        self.assertEqual(resp.status_code, 200)


# ── Customer Report Views ──────────────────────────────────────────────────

class TestCustomerReports(ViewTestBase):
    """Tests for customer report views."""

    def setUp(self):
        self.booking = create_booking(self.customer, self.user)
        self.booking2 = create_booking(self.customer2, self.user2)

    def test_customer_reports_hub(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_reports_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Reports')

    def test_customer_reports_hub_staff_redirect(self):
        self._login_staff()
        resp = self.client.get(reverse('customer_reports_hub'))
        self.assertEqual(resp.status_code, 302)

    def test_customer_summary(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_summary'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Booking Summary')

    def test_customer_summary_csv(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_summary'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_customer_routes(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_routes'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Route History')

    def test_customer_routes_csv(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_routes'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_customer_performance(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_performance'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Shipment Performance')

    def test_customer_performance_csv(self):
        self._login_customer()
        resp = self.client.get(reverse('customer_report_performance'), {'format': 'csv'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')

    def test_customer_only_sees_own_data(self):
        """Customer summary should only count their own bookings."""
        self._login_customer()
        resp = self.client.get(reverse('customer_report_summary'))
        self.assertEqual(resp.status_code, 200)
        # Total should be 1 (only customer's booking, not customer2's)
        self.assertEqual(resp.context['total'], 1)

    def test_staff_redirected_from_customer_reports(self):
        """Staff accessing customer report views should redirect to staff hub."""
        self._login_staff()
        resp = self.client.get(reverse('customer_report_summary'))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse('customer_report_routes'))
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(reverse('customer_report_performance'))
        self.assertEqual(resp.status_code, 302)
