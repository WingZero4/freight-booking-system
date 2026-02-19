"""Tests for the read API endpoints and cancel/submit policy via API."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from unittest.mock import patch

from bookings.models import (
    Booking, BookingDocument, BookingParty, Customer, Port,
    ContainerType, UserProfile,
)
from bookings.tests.helpers import get_default_org


def _setup_data():
    """Create shared test data (two customers, staff, ports)."""
    org = get_default_org()
    customer_a = Customer.objects.create(
        name='Alpha Corp', code='ALPHA1', is_active=True,
        organization=org,
    )
    customer_b = Customer.objects.create(
        name='Beta Corp', code='BETA01', is_active=True,
        organization=org,
    )
    origin = Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
    dest = Port.objects.create(code='USNYC', name='New York', country='US')
    ctype = ContainerType.objects.create(code='20GP', name='20ft GP', size_ft=20)

    staff = User.objects.create_user(
        'staffuser', 'staff@test.com', 'pass123', is_staff=True,
    )
    UserProfile.objects.create(user=staff, organization=org, role='ADMIN')
    staff_token = Token.objects.create(user=staff)

    cust_a = User.objects.create_user('cust_a', 'a@test.com', 'pass123')
    UserProfile.objects.create(
        user=cust_a, customer=customer_a, role='USER',
        organization=org,
    )
    cust_a_token = Token.objects.create(user=cust_a)

    cust_b = User.objects.create_user('cust_b', 'b@test.com', 'pass123')
    UserProfile.objects.create(
        user=cust_b, customer=customer_b, role='USER',
        organization=org,
    )
    cust_b_token = Token.objects.create(user=cust_b)

    return {
        'customer_a': customer_a,
        'customer_b': customer_b,
        'origin': origin,
        'dest': dest,
        'ctype': ctype,
        'staff': staff,
        'staff_token': staff_token,
        'cust_a': cust_a,
        'cust_a_token': cust_a_token,
        'cust_b': cust_b,
        'cust_b_token': cust_b_token,
    }


def _booking_payload(**overrides):
    """Minimal valid booking JSON payload."""
    data = {
        'transport_mode': 'SEA_FCL',
        'origin_port': 'CNSHA',
        'destination_port': 'USNYC',
        'cargo_ready_date': str(date.today() + timedelta(days=7)),
        'incoterms': 'FOB',
        'external_reference': 'TEST-REF-001',
        'container_type': '20GP',
        'container_count': 2,
        'items': [
            {
                'description': 'Test cargo',
                'quantity': 10,
                'weight_kg': '500.00',
                'package_type': 'CARTON',
            },
        ],
    }
    data.update(overrides)
    return data


# ─── List endpoint ──────────────────────────────────────────────────


class TestBookingListAPI(TestCase):

    def setUp(self):
        self.d = _setup_data()
        self.client = APIClient()

    def test_list_requires_auth(self):
        resp = self.client.get('/api/v1/bookings/')
        self.assertEqual(resp.status_code, 401)

    def test_customer_sees_own_bookings_only(self):
        # Create booking for customer A
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')

        # Create booking for customer B
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_b_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')

        # Customer A should only see 1
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.get('/api/v1/bookings/')
        self.assertEqual(resp.data['count'], 1)

    def test_staff_sees_all_bookings(self):
        # Create bookings for two different customers
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_b_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')

        # Staff sees both
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["staff_token"].key}',
        )
        resp = self.client.get('/api/v1/bookings/')
        self.assertEqual(resp.data['count'], 2)

    def test_filter_by_status(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        booking_id = resp.data['id']
        # Submit one booking
        self.client.post(f'/api/v1/bookings/{booking_id}/submit/')
        # Create another (stays DRAFT)
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')

        resp = self.client.get('/api/v1/bookings/?status=SUBMITTED')
        self.assertEqual(resp.data['count'], 1)

    def test_filter_by_transport_mode(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')
        self.client.post(
            '/api/v1/bookings/',
            _booking_payload(
                transport_mode='AIR', container_type=None, container_count=None,
            ),
            format='json',
        )

        resp = self.client.get('/api/v1/bookings/?transport_mode=AIR')
        self.assertEqual(resp.data['count'], 1)

    def test_search_by_booking_number(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        self.client.post('/api/v1/bookings/', _booking_payload(), format='json')
        resp = self.client.get('/api/v1/bookings/?search=BK-')
        self.assertGreaterEqual(resp.data['count'], 1)

    def test_pagination_structure(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        for _ in range(3):
            self.client.post(
                '/api/v1/bookings/', _booking_payload(), format='json',
            )
        resp = self.client.get('/api/v1/bookings/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('count', resp.data)
        self.assertIn('results', resp.data)
        self.assertEqual(resp.data['count'], 3)
        self.assertEqual(len(resp.data['results']), 3)


# ─── Detail endpoint ────────────────────────────────────────────────


class TestBookingDetailAPI(TestCase):

    def setUp(self):
        self.d = _setup_data()
        self.client = APIClient()
        # Create a booking for customer A
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/',
            _booking_payload(parties=[
                {'role': 'SHIPPER', 'company_name': 'Shipper Co'},
            ]),
            format='json',
        )
        self.booking_id = resp.data['id']

    def test_detail_returns_full_data(self):
        resp = self.client.get(f'/api/v1/bookings/{self.booking_id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('booking_number', resp.data)
        self.assertIn('route', resp.data)
        self.assertIn('cargo', resp.data)
        self.assertIn('timestamps', resp.data)

    def test_customer_cannot_see_other_customer_booking(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_b_token"].key}',
        )
        resp = self.client.get(f'/api/v1/bookings/{self.booking_id}/')
        self.assertEqual(resp.status_code, 404)

    def test_detail_includes_items_and_parties(self):
        resp = self.client.get(f'/api/v1/bookings/{self.booking_id}/')
        self.assertGreater(len(resp.data['cargo']['items']), 0)
        self.assertIn('shipper', resp.data['parties'])

    def test_fms_push_error_hidden_from_customer(self):
        # Set an FMS error on the booking
        booking = Booking.objects.get(pk=self.booking_id)
        booking.fms_push_error = 'Connection timeout'
        booking.save()

        resp = self.client.get(f'/api/v1/bookings/{self.booking_id}/')
        self.assertNotIn('push_error', resp.data['fms'])

    def test_fms_push_error_visible_to_staff(self):
        booking = Booking.objects.get(pk=self.booking_id)
        booking.fms_push_error = 'Connection timeout'
        booking.save()

        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["staff_token"].key}',
        )
        resp = self.client.get(f'/api/v1/bookings/{self.booking_id}/')
        self.assertEqual(resp.data['fms']['push_error'], 'Connection timeout')


# ─── Documents endpoint ─────────────────────────────────────────────


class TestDocumentAPI(TestCase):

    def setUp(self):
        self.d = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.booking_id = resp.data['id']

    def test_upload_document(self):
        pdf = SimpleUploadedFile(
            'invoice.pdf', b'%PDF-1.4 content', content_type='application/pdf',
        )
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/documents/',
            {'document_type': 'COMMERCIAL_INVOICE', 'file': pdf},
            format='multipart',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['document_type'], 'COMMERCIAL_INVOICE')

    def test_download_document(self):
        pdf = SimpleUploadedFile(
            'test.pdf', b'%PDF-1.4 content', content_type='application/pdf',
        )
        upload_resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/documents/',
            {'document_type': 'OTHER', 'file': pdf},
            format='multipart',
        )
        doc_id = upload_resp.data['id']
        resp = self.client.get(
            f'/api/v1/bookings/{self.booking_id}/documents/{doc_id}/download/',
        )
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_download_other_customer_doc(self):
        # Upload as customer A
        pdf = SimpleUploadedFile(
            'secret.pdf', b'%PDF-1.4', content_type='application/pdf',
        )
        upload_resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/documents/',
            {'document_type': 'OTHER', 'file': pdf},
            format='multipart',
        )
        doc_id = upload_resp.data['id']

        # Try to download as customer B
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_b_token"].key}',
        )
        resp = self.client.get(
            f'/api/v1/bookings/{self.booking_id}/documents/{doc_id}/download/',
        )
        self.assertEqual(resp.status_code, 404)


# ─── Cancel policy via API ──────────────────────────────────────────


class TestCancelPolicyAPI(TestCase):

    def setUp(self):
        self.d = _setup_data()
        self.client = APIClient()
        # Create and confirm a booking
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.booking_id = resp.data['id']
        # Submit as customer
        self.client.post(f'/api/v1/bookings/{self.booking_id}/submit/')
        # Confirm as staff
        booking = Booking.objects.get(pk=self.booking_id)
        booking.status = 'CONFIRMED'
        booking.save()

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_cancel_confirmed_customer_blocked(self, mock_notify):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/cancel/',
            {'reason': 'I changed my mind'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('staff', resp.data['error'].lower())

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_cancel_confirmed_staff_no_reason_blocked(self, mock_notify):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["staff_token"].key}',
        )
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/cancel/',
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('reason', resp.data['error'].lower())

    @patch('bookings.services.notifications.notify_booking_confirmed')
    def test_cancel_confirmed_staff_with_reason_ok(self, mock_notify):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["staff_token"].key}',
        )
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/cancel/',
            {'reason': 'Customer requested cancellation'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'CANCELLED')


# ─── Submit guard via API ───────────────────────────────────────────


class TestSubmitGuardAPI(TestCase):

    def setUp(self):
        self.d = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.d["cust_a_token"].key}',
        )

    def test_submit_fcl_no_container_blocked(self):
        # Create FCL booking then remove container data
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        booking_id = resp.data['id']
        booking = Booking.objects.get(pk=booking_id)
        booking.container_type = None
        booking.container_count = None
        booking.save()

        resp = self.client.post(f'/api/v1/bookings/{booking_id}/submit/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('container', resp.data['error'].lower())
