"""
Tests for Tier 2 Business Features:
  - In-App Notifications (model, module, views, context processor)
  - Shipment Tracking (milestone builder)
  - Booking Templates (model, CRUD views)
  - Staff Bulk Operations (view)
  - Context Processors (nav_active, customer_theme)
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase, RequestFactory
from django.urls import reverse
from django.utils import timezone

from bookings.models import (
    Booking, BookingItem, BookingTemplate, Notification, UserProfile,
)
from bookings.notifications import (
    notify_booking_submitted, notify_booking_confirmed,
    notify_booking_rejected, notify_booking_in_transit,
    notify_booking_completed, notify_booking_cancelled,
    notify_booking_resubmitted,
)
from bookings.views import _build_tracking_milestones
from bookings.context_processors import (
    nav_active, notifications_context, customer_theme,
)
from bookings.tests.helpers import (
    create_customer, create_user, create_port, create_container_type,
    create_booking, create_booking_item, create_party,
)


class Tier2TestBase(TestCase):
    """Shared setup for Tier 2 feature tests."""

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


# ─── Feature 1: In-App Notifications ────────────────────────────────


class TestNotificationModel(Tier2TestBase):

    def test_create_notification(self):
        booking = create_booking(self.customer, self.user)
        notif = Notification.objects.create(
            user=self.user, booking=booking,
            message='Test message',
            notification_type='BOOKING_SUBMITTED',
        )
        self.assertIsNotNone(notif.pk)
        self.assertEqual(notif.message, 'Test message')

    def test_is_read_defaults_false(self):
        notif = Notification.objects.create(
            user=self.user, message='Test',
            notification_type='GENERAL',
        )
        self.assertFalse(notif.is_read)

    def test_ordering_newest_first(self):
        n1 = Notification.objects.create(
            user=self.user, message='First', notification_type='GENERAL',
        )
        n2 = Notification.objects.create(
            user=self.user, message='Second', notification_type='GENERAL',
        )
        notifications = list(Notification.objects.filter(user=self.user))
        self.assertEqual(notifications[0].pk, n2.pk)
        self.assertEqual(notifications[1].pk, n1.pk)


class TestNotificationModule(Tier2TestBase):
    """Test that notify_booking_* functions create in-app notifications."""

    def setUp(self):
        self.booking = create_booking(self.customer, self.user)
        create_booking_item(self.booking)

    @patch('bookings.notifications._send_notification')
    def test_submitted_creates_customer_and_staff_notifications(self, mock_send):
        notify_booking_submitted(self.booking)
        customer_notifs = Notification.objects.filter(
            booking=self.booking, user=self.user,
            notification_type='BOOKING_SUBMITTED',
        )
        staff_notifs = Notification.objects.filter(
            booking=self.booking, user=self.staff,
            notification_type='BOOKING_SUBMITTED',
        )
        self.assertTrue(customer_notifs.exists())
        self.assertTrue(staff_notifs.exists())

    @patch('bookings.notifications._send_notification')
    def test_confirmed_creates_customer_notification(self, mock_send):
        notify_booking_confirmed(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_CONFIRMED',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_rejected_creates_customer_notification(self, mock_send):
        notify_booking_rejected(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_REJECTED',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_in_transit_creates_customer_notification(self, mock_send):
        notify_booking_in_transit(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_IN_TRANSIT',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_completed_creates_customer_notification(self, mock_send):
        notify_booking_completed(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_COMPLETED',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_cancelled_creates_customer_notification(self, mock_send):
        notify_booking_cancelled(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_CANCELLED',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_resubmitted_creates_customer_notification(self, mock_send):
        notify_booking_resubmitted(self.booking)
        self.assertTrue(Notification.objects.filter(
            booking=self.booking, notification_type='BOOKING_RESUBMITTED',
            user=self.user,
        ).exists())

    @patch('bookings.notifications._send_notification')
    def test_notification_message_contains_booking_number(self, mock_send):
        notify_booking_submitted(self.booking)
        notif = Notification.objects.filter(
            booking=self.booking, user=self.user,
        ).first()
        self.assertIn(self.booking.booking_number, notif.message)


class TestNotificationViews(Tier2TestBase):

    def setUp(self):
        self.booking = create_booking(self.customer, self.user)
        self.notif1 = Notification.objects.create(
            user=self.user, booking=self.booking,
            message='Test notification 1',
            notification_type='BOOKING_SUBMITTED',
        )
        self.notif2 = Notification.objects.create(
            user=self.user, booking=self.booking,
            message='Test notification 2',
            notification_type='BOOKING_CONFIRMED',
        )

    def test_notification_list_requires_login(self):
        resp = self.client.get(reverse('notification_list'))
        self.assertNotEqual(resp.status_code, 200)

    def test_notification_list_returns_200(self):
        self._login_customer()
        resp = self.client.get(reverse('notification_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test notification')

    def test_mark_read_marks_notification(self):
        self._login_customer()
        resp = self.client.post(
            reverse('notification_mark_read', args=[self.notif1.pk]),
        )
        self.notif1.refresh_from_db()
        self.assertTrue(self.notif1.is_read)

    def test_mark_read_redirects_to_booking(self):
        self._login_customer()
        resp = self.client.post(
            reverse('notification_mark_read', args=[self.notif1.pk]),
        )
        self.assertRedirects(
            resp,
            reverse('booking_detail', args=[self.booking.pk]),
        )

    def test_mark_read_other_user_denied(self):
        self._login_customer2()
        resp = self.client.post(
            reverse('notification_mark_read', args=[self.notif1.pk]),
        )
        self.assertEqual(resp.status_code, 404)

    def test_mark_read_no_booking_redirects_to_list(self):
        """Notification without a booking redirects to notification list."""
        notif = Notification.objects.create(
            user=self.user, message='General alert',
            notification_type='GENERAL',
        )
        self._login_customer()
        resp = self.client.post(
            reverse('notification_mark_read', args=[notif.pk]),
        )
        self.assertRedirects(resp, reverse('notification_list'))

    def test_mark_read_get_redirects(self):
        self._login_customer()
        resp = self.client.get(
            reverse('notification_mark_read', args=[self.notif1.pk]),
        )
        self.assertRedirects(resp, reverse('notification_list'))

    def test_mark_all_read(self):
        self._login_customer()
        self.client.post(reverse('notification_mark_all_read'))
        unread = Notification.objects.filter(
            user=self.user, is_read=False,
        ).count()
        self.assertEqual(unread, 0)


class TestNotificationsContextProcessor(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.customer = create_customer(code='CTXCUST')
        self.user = create_user(username='ctxuser', customer=self.customer)

    def test_returns_unread_count(self):
        Notification.objects.create(
            user=self.user, message='Unread', notification_type='GENERAL',
        )
        Notification.objects.create(
            user=self.user, message='Read', notification_type='GENERAL',
            is_read=True,
        )
        request = self.factory.get('/')
        request.user = self.user
        ctx = notifications_context(request)
        self.assertEqual(ctx['unread_notifications_count'], 1)
        self.assertEqual(len(ctx['recent_notifications']), 2)

    def test_anonymous_user_returns_empty(self):
        from django.contrib.auth.models import AnonymousUser
        request = self.factory.get('/')
        request.user = AnonymousUser()
        ctx = notifications_context(request)
        self.assertEqual(ctx, {})


# ─── Feature 2: Shipment Tracking Milestones ────────────────────────


class TestTrackingMilestones(Tier2TestBase):

    def setUp(self):
        self.booking = create_booking(self.customer, self.user, status='DRAFT')

    def test_draft_milestones(self):
        milestones = _build_tracking_milestones(self.booking)
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertEqual(statuses['Created'], 'completed')
        self.assertEqual(statuses['Submitted'], 'pending')
        self.assertIn('Confirmed', statuses)

    def test_submitted_milestones(self):
        self.booking.status = 'SUBMITTED'
        self.booking.submitted_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertEqual(statuses['Submitted'], 'completed')
        self.assertEqual(statuses['Confirmed'], 'pending')

    def test_confirmed_milestones(self):
        self.booking.status = 'CONFIRMED'
        self.booking.submitted_at = timezone.now()
        self.booking.confirmed_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertEqual(statuses['Confirmed'], 'completed')
        self.assertEqual(statuses['Packing'], 'pending')
        self.assertEqual(statuses['In Transit'], 'pending')
        self.assertEqual(statuses['Delivered'], 'pending')

    def test_in_transit_milestones(self):
        self.booking.status = 'IN_TRANSIT'
        self.booking.submitted_at = timezone.now()
        self.booking.confirmed_at = timezone.now()
        self.booking.in_transit_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertEqual(statuses['In Transit'], 'active')
        self.assertEqual(statuses['Delivered'], 'pending')

    def test_completed_milestones(self):
        self.booking.status = 'COMPLETED'
        self.booking.submitted_at = timezone.now()
        self.booking.confirmed_at = timezone.now()
        self.booking.in_transit_at = timezone.now()
        self.booking.completed_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertEqual(statuses['In Transit'], 'completed')
        self.assertEqual(statuses['Delivered'], 'completed')

    def test_cancelled_milestones(self):
        self.booking.status = 'CANCELLED'
        self.booking.submitted_at = timezone.now()
        self.booking.cancelled_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertIn('Cancelled', labels)
        self.assertEqual(statuses['Cancelled'], 'cancelled')

    def test_rejected_milestones(self):
        self.booking.status = 'REJECTED'
        self.booking.submitted_at = timezone.now()
        self.booking.rejected_at = timezone.now()
        milestones = _build_tracking_milestones(self.booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        self.assertIn('Rejected', labels)
        self.assertEqual(statuses['Rejected'], 'rejected')
        self.assertNotIn('Confirmed', labels)
        self.assertNotIn('In Transit', labels)
        self.assertNotIn('Delivered', labels)

    def test_booking_detail_has_tracking_tab(self):
        self._login_customer()
        self.booking.status = 'CONFIRMED'
        self.booking.submitted_at = timezone.now()
        self.booking.confirmed_at = timezone.now()
        self.booking.save()
        resp = self.client.get(
            reverse('booking_detail', args=[self.booking.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'tracking-timeline')


# ─── Feature 3: Booking Templates ───────────────────────────────────


class TestBookingTemplateModel(Tier2TestBase):

    def test_create_template(self):
        tmpl = BookingTemplate.objects.create(
            customer=self.customer,
            name='Test Template',
            template_data={'transport_mode': 'SEA_FCL'},
            created_by=self.user,
        )
        self.assertIsNotNone(tmpl.pk)
        self.assertEqual(tmpl.template_data['transport_mode'], 'SEA_FCL')

    def test_unique_constraint_same_customer_same_name(self):
        BookingTemplate.objects.create(
            customer=self.customer, name='Duplicate',
            template_data={}, created_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            BookingTemplate.objects.create(
                customer=self.customer, name='Duplicate',
                template_data={}, created_by=self.user,
            )

    def test_different_customers_same_name_ok(self):
        BookingTemplate.objects.create(
            customer=self.customer, name='Same Name',
            template_data={}, created_by=self.user,
        )
        tmpl2 = BookingTemplate.objects.create(
            customer=self.customer2, name='Same Name',
            template_data={}, created_by=self.user2,
        )
        self.assertIsNotNone(tmpl2.pk)


class TestTemplateViews(Tier2TestBase):

    def setUp(self):
        self.booking = create_booking(self.customer, self.user)
        create_booking_item(self.booking)
        self.tmpl = BookingTemplate.objects.create(
            customer=self.customer, name='My Template',
            template_data={
                'transport_mode': 'SEA_FCL',
                'origin_port_id': self.port_origin.pk,
                'destination_port_id': self.port_dest.pk,
                'container_type_id': self.container_type.pk,
                'container_count': 2,
                'incoterms': 'FOB',
                'incoterms_location': '',
                'commodity_description': 'Template cargo',
                'is_hazardous': False,
                'special_instructions': '',
                'chargeable_weight_kg': None,
                'flight_number': '',
                'items': [{
                    'description': 'Template Item',
                    'package_type': 'CARTON',
                    'quantity': 50,
                    'weight_kg': '250.00',
                    'hs_code': '', 'volume_cbm': None,
                    'length_cm': None, 'width_cm': None, 'height_cm': None,
                    'marks_and_numbers': '', 'is_hazardous': False,
                    'un_number': '', 'imo_class': '', 'country_of_origin': '',
                }],
                'parties': [],
            },
            created_by=self.user,
        )

    def test_template_list_returns_200(self):
        self._login_customer()
        resp = self.client.get(reverse('template_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'My Template')

    def test_template_list_search(self):
        self._login_customer()
        resp = self.client.get(reverse('template_list') + '?q=My')
        self.assertContains(resp, 'My Template')
        resp = self.client.get(reverse('template_list') + '?q=Nonexistent')
        self.assertNotContains(resp, 'My Template')

    def test_template_list_customer_isolation(self):
        self._login_customer2()
        resp = self.client.get(reverse('template_list'))
        self.assertNotContains(resp, 'My Template')

    def test_template_list_staff_denied(self):
        self._login_staff()
        resp = self.client.get(reverse('template_list'))
        self.assertRedirects(resp, reverse('dashboard'))

    def test_template_save(self):
        self._login_customer()
        resp = self.client.post(
            reverse('template_save', args=[self.booking.pk]),
            {'template_name': 'New Template'},
        )
        self.assertTrue(
            BookingTemplate.objects.filter(
                customer=self.customer, name='New Template',
            ).exists()
        )

    def test_template_save_empty_name(self):
        self._login_customer()
        resp = self.client.post(
            reverse('template_save', args=[self.booking.pk]),
            {'template_name': '   '},
            follow=True,
        )
        self.assertContains(resp, 'provide a template name')
        self.assertEqual(BookingTemplate.objects.filter(name='').count(), 0)

    def test_template_save_duplicate_name_error(self):
        self._login_customer()
        resp = self.client.post(
            reverse('template_save', args=[self.booking.pk]),
            {'template_name': 'My Template'},
            follow=True,
        )
        self.assertContains(resp, 'already exists')

    def test_template_save_other_customer_booking_denied(self):
        other_booking = create_booking(self.customer2, self.user2)
        self._login_customer()
        resp = self.client.post(
            reverse('template_save', args=[other_booking.pk]),
            {'template_name': 'Stolen'},
        )
        self.assertEqual(resp.status_code, 404)

    def test_template_delete(self):
        self._login_customer()
        resp = self.client.post(
            reverse('template_delete', args=[self.tmpl.pk]),
        )
        self.assertFalse(BookingTemplate.objects.filter(pk=self.tmpl.pk).exists())

    def test_template_delete_other_customer_denied(self):
        self._login_customer2()
        resp = self.client.post(
            reverse('template_delete', args=[self.tmpl.pk]),
        )
        self.assertEqual(resp.status_code, 404)

    def test_create_from_template_get(self):
        self._login_customer()
        resp = self.client.get(
            reverse('booking_create_from_template', args=[self.tmpl.pk]),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Template cargo')

    def test_create_from_template_post(self):
        self._login_customer()
        post_data = {
            'transport_mode': 'SEA_FCL',
            'origin_port': self.port_origin.pk,
            'destination_port': self.port_dest.pk,
            'cargo_ready_date': (date.today() + timedelta(days=14)).isoformat(),
            'container_type': self.container_type.pk,
            'container_count': 2,
            'incoterms': 'FOB',
            'incoterms_location': '',
            'commodity_description': 'From template',
            'is_hazardous': '',
            'external_reference': '',
            'special_instructions': '',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '1',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-description': 'Template Item',
            'items-0-package_type': 'CARTON',
            'items-0-quantity': '50',
            'items-0-weight_kg': '250.00',
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
        initial_count = Booking.objects.count()
        resp = self.client.post(
            reverse('booking_create_from_template', args=[self.tmpl.pk]),
            post_data,
        )
        self.assertEqual(Booking.objects.count(), initial_count + 1)
        new_booking = Booking.objects.order_by('-created_at').first()
        self.assertEqual(new_booking.commodity_description, 'From template')

    def test_create_from_template_other_customer_denied(self):
        self._login_customer2()
        resp = self.client.get(
            reverse('booking_create_from_template', args=[self.tmpl.pk]),
        )
        self.assertEqual(resp.status_code, 404)


# ─── Feature 4: Staff Bulk Operations ───────────────────────────────


class TestBulkOperations(Tier2TestBase):

    def _create_submitted_bookings(self, count=3):
        bookings = []
        for i in range(count):
            b = create_booking(self.customer, self.user, status='SUBMITTED')
            b.submitted_at = timezone.now()
            b.save(update_fields=['submitted_at'])
            create_booking_item(b)
            bookings.append(b)
        return bookings

    @patch('bookings.services.BookingService._log')
    @patch('bookings.notifications.notify_booking_confirmed')
    def test_bulk_confirm(self, mock_notify, mock_log):
        self._login_staff()
        bookings = self._create_submitted_bookings(3)
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'confirm',
            'selected_bookings': [b.pk for b in bookings],
        })
        self.assertRedirects(resp, reverse('booking_list'))
        for b in bookings:
            b.refresh_from_db()
            self.assertEqual(b.status, 'CONFIRMED')

    @patch('bookings.services.BookingService._log')
    @patch('bookings.notifications.notify_booking_in_transit')
    def test_bulk_in_transit(self, mock_notify, mock_log):
        self._login_staff()
        bookings = self._create_submitted_bookings(3)
        # First set to PACKING (customer approved)
        for b in bookings:
            b.status = 'PACKING'
            b.packing_at = timezone.now()
            b.save(update_fields=['status', 'packing_at'])
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'in_transit',
            'selected_bookings': [b.pk for b in bookings],
        })
        for b in bookings:
            b.refresh_from_db()
            self.assertEqual(b.status, 'IN_TRANSIT')

    @patch('bookings.services.BookingService._log')
    @patch('bookings.notifications.notify_booking_completed')
    def test_bulk_complete(self, mock_notify, mock_log):
        self._login_staff()
        bookings = self._create_submitted_bookings(3)
        for b in bookings:
            b.status = 'IN_TRANSIT'
            b.confirmed_at = timezone.now()
            b.in_transit_at = timezone.now()
            b.save(update_fields=['status', 'confirmed_at', 'in_transit_at'])
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'complete',
            'selected_bookings': [b.pk for b in bookings],
        })
        for b in bookings:
            b.refresh_from_db()
            self.assertEqual(b.status, 'COMPLETED')

    def test_bulk_wrong_status_skipped(self):
        self._login_staff()
        booking = create_booking(self.customer, self.user, status='DRAFT')
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'confirm',
            'selected_bookings': [booking.pk],
        }, follow=True)
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'DRAFT')
        self.assertContains(resp, 'skipped')

    def test_bulk_customer_denied(self):
        self._login_customer()
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'confirm',
            'selected_bookings': [],
        })
        self.assertRedirects(resp, reverse('dashboard'))

    def test_bulk_get_redirects(self):
        self._login_staff()
        resp = self.client.get(reverse('ops_bulk_action'))
        self.assertRedirects(resp, reverse('booking_list'))

    def test_bulk_empty_selection(self):
        self._login_staff()
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'confirm',
        }, follow=True)
        self.assertContains(resp, 'No action or bookings selected')

    def test_bulk_invalid_action(self):
        self._login_staff()
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'invalid_action',
            'selected_bookings': ['1'],
        }, follow=True)
        self.assertContains(resp, 'Invalid bulk action')

    def test_bulk_nonexistent_booking(self):
        self._login_staff()
        resp = self.client.post(reverse('ops_bulk_action'), {
            'bulk_action': 'confirm',
            'selected_bookings': ['99999'],
        }, follow=True)
        self.assertContains(resp, 'error')

    def test_staff_sees_bulk_checkboxes(self):
        self._login_staff()
        create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_list'))
        self.assertContains(resp, 'selectAll')

    def test_customer_no_bulk_checkboxes(self):
        self._login_customer()
        create_booking(self.customer, self.user)
        resp = self.client.get(reverse('booking_list'))
        self.assertNotContains(resp, 'selectAll')


# ─── Context Processors ─────────────────────────────────────────────


class TestNavActiveProcessor(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.customer = create_customer(code='NAVCUST')
        self.user = create_user(username='navuser', customer=self.customer)

    def _request(self, path):
        request = self.factory.get(path)
        request.user = self.user
        return request

    def test_bookings_path(self):
        ctx = nav_active(self._request('/bookings/'))
        self.assertEqual(ctx['nav_active'], 'bookings')

    def test_new_booking_path(self):
        ctx = nav_active(self._request('/bookings/create/'))
        self.assertEqual(ctx['nav_active'], 'new_booking')

    def test_ops_path(self):
        ctx = nav_active(self._request('/ops/'))
        self.assertEqual(ctx['nav_active'], 'dashboard')

    def test_templates_path(self):
        ctx = nav_active(self._request('/templates/'))
        self.assertEqual(ctx['nav_active'], 'templates')

    def test_notifications_path(self):
        ctx = nav_active(self._request('/notifications/'))
        self.assertEqual(ctx['nav_active'], 'notifications')

    def test_parties_path(self):
        ctx = nav_active(self._request('/parties/'))
        self.assertEqual(ctx['nav_active'], 'parties')

    def test_staff_sees_pending_count(self):
        staff = create_user(username='navstaff', is_staff=True)
        # Create a pending registration
        pending_user = create_user(
            username='pendinguser', customer=self.customer,
        )
        UserProfile.objects.filter(user=pending_user).update(
            approval_status='PENDING',
        )
        request = self.factory.get('/ops/')
        request.user = staff
        ctx = nav_active(request)
        self.assertEqual(ctx['pending_registrations_count'], 1)


class TestCustomerThemeProcessor(TestCase):

    def setUp(self):
        self.factory = RequestFactory()

    def test_default_theme_for_staff(self):
        staff = create_user(username='themestaff', is_staff=True)
        request = self.factory.get('/')
        request.user = staff
        ctx = customer_theme(request)
        self.assertEqual(ctx['theme_primary'], '#1E2A4A')
        self.assertEqual(ctx['theme_accent'], '#DC3545')
        self.assertEqual(ctx['theme_portal_name'], 'Freight Booking')

    def test_customer_branding_overrides(self):
        customer = create_customer(
            code='BRANDCUST', name='Branded',
            primary_color='#FF0000', accent_color='#00FF00',
            portal_name='Branded Portal',
        )
        user = create_user(username='branduser', customer=customer)
        request = self.factory.get('/')
        request.user = user
        ctx = customer_theme(request)
        self.assertEqual(ctx['theme_primary'], '#FF0000')
        self.assertEqual(ctx['theme_accent'], '#00FF00')
        self.assertEqual(ctx['theme_portal_name'], 'Branded Portal')
