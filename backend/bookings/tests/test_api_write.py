"""Tests for the write API endpoints (Phase 3)."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from bookings.models import (
    Booking, BookingItem, Customer, Port, ContainerType, UserProfile,
)
from bookings.tests.helpers import get_default_org


def _setup_data():
    """Create shared test data."""
    org = get_default_org()
    customer = Customer.objects.create(
        name='Test Corp', code='TEST01', is_active=True,
        organization=org,
    )
    origin = Port.objects.create(code='CNSHA', name='Shanghai', country='CN')
    dest = Port.objects.create(code='USNYC', name='New York', country='US')
    ctype = ContainerType.objects.create(code='20GP', name='20ft GP', size_ft=20)

    # Staff user
    staff = User.objects.create_user(
        'staffuser', 'staff@test.com', 'pass123', is_staff=True,
    )
    UserProfile.objects.create(user=staff, organization=org, role='ADMIN')
    staff_token = Token.objects.create(user=staff)

    # Customer user
    cust_user = User.objects.create_user(
        'custuser', 'cust@test.com', 'pass123',
    )
    UserProfile.objects.create(
        user=cust_user, customer=customer, role='USER',
        organization=org,
    )
    cust_token = Token.objects.create(user=cust_user)

    return {
        'customer': customer,
        'origin': origin,
        'dest': dest,
        'ctype': ctype,
        'staff': staff,
        'staff_token': staff_token,
        'cust_user': cust_user,
        'cust_token': cust_token,
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


class TestBookingCreateAPI(TestCase):

    def setUp(self):
        self.data = _setup_data()
        self.client = APIClient()

    def test_create_booking_as_customer(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn('booking_number', resp.data)
        self.assertEqual(resp.data['status'], 'DRAFT')

    def test_create_booking_sets_source_channel_api(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        booking = Booking.objects.first()
        self.assertEqual(booking.source_channel, 'API')

    def test_create_booking_with_items(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        payload = _booking_payload(items=[
            {'description': 'Item A', 'quantity': 5, 'weight_kg': '100.00'},
            {'description': 'Item B', 'quantity': 3, 'weight_kg': '200.00'},
        ])
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 201)
        booking = Booking.objects.first()
        self.assertEqual(booking.items.count(), 2)

    def test_create_booking_staff_with_customer_code(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["staff_token"].key}',
        )
        payload = _booking_payload(customer_code='TEST01')
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 201)

    def test_create_booking_staff_without_customer_code_fails(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["staff_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_booking_same_ports_fails(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        payload = _booking_payload(
            origin_port='CNSHA', destination_port='CNSHA',
        )
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_booking_sea_fcl_without_container_fails(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        payload = _booking_payload(
            container_type=None, container_count=None,
        )
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_booking_air_without_container_succeeds(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        payload = _booking_payload(
            transport_mode='AIR',
            container_type=None,
            container_count=None,
        )
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 201)

    def test_create_booking_no_items_fails(self):
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        payload = _booking_payload(items=[])
        resp = self.client.post(
            '/api/v1/bookings/', payload, format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_fails(self):
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.assertEqual(resp.status_code, 401)


class TestBookingUpdateAPI(TestCase):

    def setUp(self):
        self.data = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        # Create a draft booking
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.booking_id = resp.data['id']

    def test_update_draft_booking(self):
        resp = self.client.patch(
            f'/api/v1/bookings/{self.booking_id}/',
            {'commodity_description': 'Updated cargo'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        booking = Booking.objects.get(pk=self.booking_id)
        self.assertEqual(booking.commodity_description, 'Updated cargo')

    def test_update_replaces_items(self):
        resp = self.client.patch(
            f'/api/v1/bookings/{self.booking_id}/',
            {'items': [
                {'description': 'New item', 'quantity': 1, 'weight_kg': '50.00'},
            ]},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        booking = Booking.objects.get(pk=self.booking_id)
        self.assertEqual(booking.items.count(), 1)
        self.assertEqual(booking.items.first().description, 'New item')

    def test_update_non_draft_fails(self):
        # Confirm the booking (submit then confirm via DB — service allows DRAFT+SUBMITTED updates)
        self.client.post(f'/api/v1/bookings/{self.booking_id}/submit/')
        Booking.objects.filter(pk=self.booking_id).update(status='CONFIRMED')
        resp = self.client.patch(
            f'/api/v1/bookings/{self.booking_id}/',
            {'commodity_description': 'Should fail'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)


class TestBookingSubmitAPI(TestCase):

    def setUp(self):
        self.data = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.booking_id = resp.data['id']

    def test_submit_draft_success(self):
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/submit/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'SUBMITTED')

    def test_submit_without_reference_fails(self):
        booking = Booking.objects.get(pk=self.booking_id)
        booking.external_reference = ''
        booking.save()
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/submit/',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('reference', resp.data['error'].lower())

    def test_submit_twice_fails(self):
        self.client.post(f'/api/v1/bookings/{self.booking_id}/submit/')
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/submit/',
        )
        self.assertEqual(resp.status_code, 400)


class TestBookingCancelAPI(TestCase):

    def setUp(self):
        self.data = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        resp = self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        self.booking_id = resp.data['id']

    def test_cancel_draft(self):
        resp = self.client.post(
            f'/api/v1/bookings/{self.booking_id}/cancel/',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'CANCELLED')


class TestBookingListFilter(TestCase):

    def setUp(self):
        self.data = _setup_data()
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Token {self.data["cust_token"].key}',
        )
        # Create two bookings
        self.client.post(
            '/api/v1/bookings/', _booking_payload(), format='json',
        )
        payload2 = _booking_payload(transport_mode='AIR',
                                     container_type=None,
                                     container_count=None)
        self.client.post(
            '/api/v1/bookings/', payload2, format='json',
        )

    def test_filter_by_transport_mode(self):
        resp = self.client.get('/api/v1/bookings/?transport_mode=AIR')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 1)

    def test_filter_by_status(self):
        resp = self.client.get('/api/v1/bookings/?status=DRAFT')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 2)

    def test_search(self):
        resp = self.client.get('/api/v1/bookings/?search=BK-')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(resp.data['count'], 1)
