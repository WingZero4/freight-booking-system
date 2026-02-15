"""
End-to-end test for Tier 2 Business Features.

Run on PythonAnywhere:
    cd ~/freight-booking-system/backend
    source ~/.virtualenvs/freight-env/bin/activate
    python test_tier2.py

Tests: In-App Notifications, Shipment Tracking, Booking Templates, Bulk Operations.
Cleans up all test data when done.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.utils import timezone

from bookings.models import (
    Booking, BookingItem, Customer, Port, ContainerType,
    Notification, BookingTemplate, UserProfile, BookingParty, Party,
)
from bookings.notifications import (
    notify_booking_submitted, notify_booking_confirmed,
    notify_booking_rejected, notify_booking_in_transit,
    notify_booking_completed, notify_booking_cancelled,
    notify_booking_resubmitted,
)
from bookings.views import _build_tracking_milestones
from bookings.services import BookingService
from bookings.context_processors import notifications_context


def header(msg):
    print(f'\n{"=" * 60}')
    print(f'  {msg}')
    print(f'{"=" * 60}')


def check(label, condition):
    status = 'PASS' if condition else 'FAIL'
    print(f'  [{status}] {label}')
    return condition


def main():
    all_pass = True

    # ── Setup ──────────────────────────────────────────────────
    header('Setup: Finding test data')

    customer = Customer.objects.first()
    if not customer:
        print('  ERROR: No customers in database.')
        sys.exit(1)

    # Find or create customer user
    customer_profile = UserProfile.objects.filter(
        customer=customer, user__is_active=True
    ).select_related('user').first()
    if not customer_profile:
        print('  ERROR: No active customer user found.')
        sys.exit(1)
    customer_user = customer_profile.user

    # Find staff user (no customer association = staff/ops)
    staff_profile = UserProfile.objects.filter(
        customer__isnull=True, user__is_active=True
    ).select_related('user').first()
    if not staff_profile:
        print('  ERROR: No active staff user found.')
        sys.exit(1)
    staff_user = staff_profile.user

    print(f'  Customer: {customer.code} ({customer.name})')
    print(f'  Customer user: {customer_user.username}')
    print(f'  Staff user: {staff_user.username}')

    # Find ports and container type for test booking
    origin = Port.objects.filter(is_active=True).first()
    destination = Port.objects.filter(is_active=True).exclude(pk=origin.pk).first()
    container_type = ContainerType.objects.first()

    # Track created objects for cleanup
    created_bookings = []
    created_notifications_before = Notification.objects.count()

    # Pre-configure Django test client settings
    from django.conf import settings
    _ssl_redirect = getattr(settings, 'SECURE_SSL_REDIRECT', False)

    try:
        # ── Feature 1: In-App Notifications ──────────────────
        header('Feature 1: In-App Notifications')

        # Create a test booking
        test_booking = Booking(
            customer=customer,
            created_by=customer_user,
            origin_port=origin,
            destination_port=destination,
            container_type=container_type,
            container_count=1,
            cargo_ready_date=timezone.now().date(),
            transport_mode='SEA_FCL',
            incoterms='FOB',
            status='DRAFT',
            source_channel='WEB',
        )
        test_booking.save()
        created_bookings.append(test_booking)
        print(f'  Created test booking: {test_booking.booking_number}')

        # Clear any existing notifications for clean test
        Notification.objects.filter(booking=test_booking).delete()

        # Test 1.1: notify_booking_submitted creates notifications
        notify_booking_submitted(test_booking)
        customer_notifs = Notification.objects.filter(
            booking=test_booking, notification_type='BOOKING_SUBMITTED',
            user=customer_user,
        )
        staff_notifs = Notification.objects.filter(
            booking=test_booking, notification_type='BOOKING_SUBMITTED',
            user=staff_user,
        )
        all_pass &= check(
            'notify_booking_submitted creates customer notification',
            customer_notifs.exists(),
        )
        all_pass &= check(
            'notify_booking_submitted creates staff notification',
            staff_notifs.exists(),
        )
        notif = customer_notifs.first()
        all_pass &= check(
            'Notification has correct message',
            test_booking.booking_number in notif.message,
        )
        all_pass &= check('Notification is_read defaults to False', not notif.is_read)
        all_pass &= check('Notification links to booking', notif.booking_id == test_booking.pk)

        # Test 1.2: All 7 notification types create records
        Notification.objects.filter(booking=test_booking).delete()

        notify_booking_confirmed(test_booking)
        all_pass &= check(
            'notify_booking_confirmed creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_CONFIRMED').exists(),
        )

        notify_booking_rejected(test_booking)
        all_pass &= check(
            'notify_booking_rejected creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_REJECTED').exists(),
        )

        notify_booking_in_transit(test_booking)
        all_pass &= check(
            'notify_booking_in_transit creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_IN_TRANSIT').exists(),
        )

        notify_booking_completed(test_booking)
        all_pass &= check(
            'notify_booking_completed creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_COMPLETED').exists(),
        )

        notify_booking_cancelled(test_booking)
        all_pass &= check(
            'notify_booking_cancelled creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_CANCELLED').exists(),
        )

        notify_booking_resubmitted(test_booking)
        all_pass &= check(
            'notify_booking_resubmitted creates notification',
            Notification.objects.filter(booking=test_booking, notification_type='BOOKING_RESUBMITTED').exists(),
        )

        # Test 1.3: Context processor returns correct data
        factory = RequestFactory()
        request = factory.get('/')
        request.user = customer_user
        ctx = notifications_context(request)
        all_pass &= check(
            'Context processor returns unread_notifications_count',
            'unread_notifications_count' in ctx and ctx['unread_notifications_count'] > 0,
        )
        all_pass &= check(
            'Context processor returns recent_notifications',
            'recent_notifications' in ctx,
        )

        # Test 1.4: Mark read
        notif = Notification.objects.filter(
            user=customer_user, booking=test_booking, is_read=False
        ).first()
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        notif.refresh_from_db()
        all_pass &= check('Notification mark read works', notif.is_read)

        # Test 1.5: Mark all read
        Notification.objects.filter(
            user=customer_user, is_read=False
        ).update(is_read=True)
        unread = Notification.objects.filter(user=customer_user, is_read=False).count()
        all_pass &= check('Mark all read works', unread == 0)

        # ── Feature 2: Shipment Tracking ──────────────────────
        header('Feature 2: Shipment Tracking Milestones')

        # Test 2.1: DRAFT booking milestones
        test_booking.status = 'DRAFT'
        test_booking.submitted_at = None
        test_booking.confirmed_at = None
        test_booking.in_transit_at = None
        test_booking.completed_at = None
        test_booking.cancelled_at = None
        test_booking.rejected_at = None
        milestones = _build_tracking_milestones(test_booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check(
            f'DRAFT milestones: {labels}',
            labels == ['Created', 'Submitted', 'Confirmed'],
        )
        all_pass &= check('DRAFT: Created=completed', statuses['Created'] == 'completed')
        all_pass &= check('DRAFT: Submitted=pending', statuses['Submitted'] == 'pending')

        # Test 2.2: SUBMITTED booking milestones
        test_booking.status = 'SUBMITTED'
        test_booking.submitted_at = timezone.now()
        milestones = _build_tracking_milestones(test_booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check(
            f'SUBMITTED milestones: {labels}',
            'Submitted' in labels and 'Confirmed' in labels,
        )
        all_pass &= check('SUBMITTED: Submitted=completed', statuses['Submitted'] == 'completed')
        all_pass &= check('SUBMITTED: Confirmed=pending', statuses['Confirmed'] == 'pending')

        # Test 2.3: CONFIRMED booking milestones
        test_booking.status = 'CONFIRMED'
        test_booking.confirmed_at = timezone.now()
        milestones = _build_tracking_milestones(test_booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check(
            f'CONFIRMED milestones: {labels}',
            'In Transit' in labels and 'Delivered' in labels,
        )
        all_pass &= check('CONFIRMED: Confirmed=completed', statuses['Confirmed'] == 'completed')
        all_pass &= check('CONFIRMED: In Transit=pending', statuses['In Transit'] == 'pending')

        # Test 2.4: IN_TRANSIT booking milestones
        test_booking.status = 'IN_TRANSIT'
        test_booking.in_transit_at = timezone.now()
        milestones = _build_tracking_milestones(test_booking)
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check('IN_TRANSIT: In Transit=active', statuses['In Transit'] == 'active')
        all_pass &= check('IN_TRANSIT: Delivered=pending', statuses['Delivered'] == 'pending')

        # Test 2.5: COMPLETED booking milestones
        test_booking.status = 'COMPLETED'
        test_booking.completed_at = timezone.now()
        milestones = _build_tracking_milestones(test_booking)
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check('COMPLETED: Delivered=completed', statuses['Delivered'] == 'completed')
        all_pass &= check('COMPLETED: In Transit=completed', statuses['In Transit'] == 'completed')

        # Test 2.6: CANCELLED booking milestones
        test_booking.status = 'CANCELLED'
        test_booking.cancelled_at = timezone.now()
        milestones = _build_tracking_milestones(test_booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check('CANCELLED: has Cancelled milestone', 'Cancelled' in labels)
        all_pass &= check('CANCELLED: Cancelled=cancelled', statuses['Cancelled'] == 'cancelled')

        # Test 2.7: REJECTED booking milestones
        test_booking.status = 'REJECTED'
        test_booking.rejected_at = timezone.now()
        test_booking.confirmed_at = None
        test_booking.in_transit_at = None
        test_booking.completed_at = None
        test_booking.cancelled_at = None
        milestones = _build_tracking_milestones(test_booking)
        labels = [m['label'] for m in milestones]
        statuses = {m['label']: m['status'] for m in milestones}
        all_pass &= check('REJECTED: has Rejected milestone', 'Rejected' in labels)
        all_pass &= check('REJECTED: Rejected=rejected', statuses['Rejected'] == 'rejected')
        all_pass &= check(
            'REJECTED: no Confirmed/In Transit/Delivered',
            'Confirmed' not in labels and 'In Transit' not in labels,
        )

        # ── Feature 3: Booking Templates ──────────────────────
        header('Feature 3: Booking Templates')

        # Reset booking to a usable state
        test_booking.status = 'DRAFT'
        test_booking.commodity_description = 'Test cargo for template'
        test_booking.special_instructions = 'Handle with care'
        test_booking.save()

        # Add a cargo item
        test_item = BookingItem.objects.create(
            booking=test_booking,
            description='Test Widget',
            package_type='CARTON',
            quantity=100,
            weight_kg=500,
        )

        # Test 3.1: Save as template
        template_data = {
            'transport_mode': test_booking.transport_mode,
            'origin_port_id': test_booking.origin_port_id,
            'destination_port_id': test_booking.destination_port_id,
            'container_type_id': test_booking.container_type_id,
            'container_count': test_booking.container_count,
            'chargeable_weight_kg': str(test_booking.chargeable_weight_kg) if test_booking.chargeable_weight_kg else None,
            'flight_number': test_booking.flight_number or '',
            'incoterms': test_booking.incoterms,
            'incoterms_location': test_booking.incoterms_location or '',
            'commodity_description': test_booking.commodity_description or '',
            'is_hazardous': test_booking.is_hazardous,
            'special_instructions': test_booking.special_instructions or '',
            'items': [{
                'description': test_item.description,
                'package_type': test_item.package_type,
                'quantity': test_item.quantity,
                'weight_kg': str(test_item.weight_kg),
                'hs_code': '',
                'volume_cbm': None,
                'length_cm': None,
                'width_cm': None,
                'height_cm': None,
                'marks_and_numbers': '',
                'is_hazardous': False,
                'un_number': '',
                'imo_class': '',
                'country_of_origin': '',
            }],
            'parties': [],
        }

        tmpl = BookingTemplate.objects.create(
            customer=customer,
            name='Test Template T2',
            template_data=template_data,
            created_by=customer_user,
        )
        all_pass &= check('Template created successfully', tmpl.pk is not None)
        all_pass &= check('Template name saved', tmpl.name == 'Test Template T2')
        all_pass &= check(
            'Template data has items',
            len(tmpl.template_data.get('items', [])) == 1,
        )
        all_pass &= check(
            'Template data has transport_mode',
            tmpl.template_data['transport_mode'] == 'SEA_FCL',
        )

        # Test 3.2: Unique constraint
        duplicate_created = False
        try:
            from django.db import IntegrityError
            BookingTemplate.objects.create(
                customer=customer,
                name='Test Template T2',
                template_data={},
                created_by=customer_user,
            )
            duplicate_created = True
        except IntegrityError:
            pass
        all_pass &= check('Unique constraint prevents duplicate name', not duplicate_created)

        # Test 3.3: Template data deserialization
        tmpl.refresh_from_db()
        data = tmpl.template_data
        all_pass &= check('Template data is a dict', isinstance(data, dict))
        all_pass &= check(
            'Template items accessible',
            data['items'][0]['description'] == 'Test Widget',
        )

        # Test 3.4: Customer isolation
        other_customer_templates = BookingTemplate.objects.exclude(customer=customer)
        # Just verify our template is scoped correctly
        my_templates = BookingTemplate.objects.filter(customer=customer, name='Test Template T2')
        all_pass &= check('Template scoped to customer', my_templates.count() == 1)

        # ── Feature 4: Bulk Operations ─────────────────────────
        header('Feature 4: Staff Bulk Operations')

        # Create 3 SUBMITTED bookings for bulk testing
        bulk_bookings = []
        for i in range(3):
            b = Booking(
                customer=customer,
                created_by=customer_user,
                origin_port=origin,
                destination_port=destination,
                container_type=container_type,
                container_count=1,
                cargo_ready_date=timezone.now().date(),
                transport_mode='SEA_FCL',
                incoterms='FOB',
                status='SUBMITTED',
                submitted_at=timezone.now(),
                source_channel='WEB',
            )
            b.save()
            bulk_bookings.append(b)
            created_bookings.append(b)
        print(f'  Created 3 SUBMITTED bookings for bulk test')

        # Test 4.1: Bulk confirm
        success = 0
        skip = 0
        for b in bulk_bookings:
            if b.status == 'SUBMITTED':
                BookingService.confirm_booking(b, user=staff_user)
                b.refresh_from_db()
                if b.status == 'CONFIRMED':
                    success += 1
                else:
                    skip += 1
        all_pass &= check(f'Bulk confirm: {success}/3 confirmed', success == 3)

        # Test 4.2: Wrong status skip
        skip_booking = bulk_bookings[0]
        skip_booking.refresh_from_db()
        all_pass &= check(
            'Already confirmed booking has status CONFIRMED',
            skip_booking.status == 'CONFIRMED',
        )
        # Trying to confirm again should raise ValueError
        raised = False
        try:
            BookingService.confirm_booking(skip_booking, user=staff_user)
        except ValueError:
            raised = True
        all_pass &= check('Confirm on CONFIRMED raises ValueError', raised)

        # Test 4.3: Bulk mark in transit
        success = 0
        for b in bulk_bookings:
            b.refresh_from_db()
            if b.status == 'CONFIRMED':
                BookingService.mark_in_transit(b, user=staff_user)
                b.refresh_from_db()
                if b.status == 'IN_TRANSIT':
                    success += 1
        all_pass &= check(f'Bulk in transit: {success}/3 marked', success == 3)

        # Test 4.4: Bulk complete
        success = 0
        for b in bulk_bookings:
            b.refresh_from_db()
            if b.status == 'IN_TRANSIT':
                BookingService.complete_booking(b, user=staff_user)
                b.refresh_from_db()
                if b.status == 'COMPLETED':
                    success += 1
        all_pass &= check(f'Bulk complete: {success}/3 completed', success == 3)

        # ── Feature 1+4 Integration: Bulk ops create notifications ─
        header('Integration: Bulk ops created notifications')

        for b in bulk_bookings:
            confirmed_notifs = Notification.objects.filter(
                booking=b, notification_type='BOOKING_CONFIRMED',
            ).count()
            all_pass &= check(
                f'{b.booking_number}: confirmed notification exists',
                confirmed_notifs > 0,
            )

        # ── HTTP Integration Tests via Django Test Client ──────
        header('HTTP Integration: Django Test Client')

        from django.test import Client
        if 'testserver' not in settings.ALLOWED_HOSTS:
            settings.ALLOWED_HOSTS.append('testserver')
        # Disable SSL redirect for test client (it makes HTTP requests)
        settings.SECURE_SSL_REDIRECT = False

        client = Client()
        client.force_login(customer_user)

        # Test: Notification list page loads
        resp = client.get('/notifications/')
        if resp.status_code != 200:
            print(f'    DEBUG: /notifications/ returned {resp.status_code}')
            if hasattr(resp, 'url'):
                print(f'    DEBUG: redirect to {resp.url}')
        all_pass &= check('Notification list page loads (200)', resp.status_code == 200)
        all_pass &= check(
            'Notification list has page_obj',
            b'Notifications' in resp.content,
        )

        # Test: Mark all read
        resp = client.post('/notifications/mark-all-read/', follow=True)
        all_pass &= check('Mark all read redirects (200)', resp.status_code == 200)

        # Test: Template list page loads
        resp = client.get('/templates/')
        all_pass &= check('Template list page loads (200)', resp.status_code == 200)
        all_pass &= check(
            'Template list shows our template',
            b'Test Template T2' in resp.content,
        )

        # Test: Create from template page loads
        resp = client.get(f'/templates/{tmpl.id}/create/')
        all_pass &= check('Create from template page loads (200)', resp.status_code == 200)
        all_pass &= check(
            'Form is pre-filled with template data',
            b'Test cargo for template' in resp.content or b'SEA_FCL' in resp.content,
        )

        # Test: Booking detail tracking tab
        test_booking.status = 'CONFIRMED'
        test_booking.submitted_at = timezone.now()
        test_booking.confirmed_at = timezone.now()
        test_booking.save()
        resp = client.get(f'/bookings/{test_booking.id}/?tab=tracking')
        all_pass &= check('Booking detail loads with tracking tab (200)', resp.status_code == 200)
        all_pass &= check(
            'Tracking tab has milestone content',
            b'tracking-timeline' in resp.content,
        )

        # Test: Save as template via POST
        resp = client.post(
            f'/bookings/{test_booking.id}/save-template/',
            {'template_name': 'HTTP Test Template'},
            follow=True,
        )
        if resp.status_code != 200:
            print(f'    DEBUG: save-template returned {resp.status_code}')
        all_pass &= check('Save as template works (200)', resp.status_code == 200)
        http_tmpl = BookingTemplate.objects.filter(
            customer=customer, name='HTTP Test Template'
        ).first()
        if http_tmpl is None:
            # Check if the form had errors
            if hasattr(resp, 'context') and resp.context and 'form' in resp.context:
                print(f'    DEBUG: form errors = {resp.context["form"].errors}')
            print(f'    DEBUG: response URL chain = {getattr(resp, "redirect_chain", "N/A")}')
        all_pass &= check('Template created via HTTP', http_tmpl is not None)

        # Test: Staff bulk action page
        client.force_login(staff_user)
        resp = client.get('/bookings/')
        all_pass &= check('Staff booking list loads (200)', resp.status_code == 200)
        all_pass &= check(
            'Staff sees bulk action checkbox',
            b'selectAll' in resp.content,
        )

        # Test: Customer cannot see bulk checkboxes
        client.force_login(customer_user)
        resp = client.get('/bookings/')
        all_pass &= check(
            'Customer does NOT see bulk checkboxes',
            b'selectAll' not in resp.content,
        )

        # Test: Staff access to template list denied
        client.force_login(staff_user)
        resp = client.get('/templates/', follow=True)
        all_pass &= check(
            'Staff redirected from template list',
            (resp.status_code == 200 and b'Templates are only available' in resp.content)
            or bool(resp.redirect_chain),
        )

    finally:
        # Restore SSL redirect setting
        settings.SECURE_SSL_REDIRECT = _ssl_redirect

        # ── Cleanup ────────────────────────────────────────────
        header('Cleanup')

        # Delete test notifications
        for b in created_bookings:
            Notification.objects.filter(booking=b).delete()
        # Delete remaining test notifications for our users
        Notification.objects.filter(
            user=customer_user,
            created_at__gte=timezone.now() - __import__('datetime').timedelta(minutes=10),
            message__contains='TEST-',
        ).delete()

        # Delete test templates
        BookingTemplate.objects.filter(customer=customer, name='Test Template T2').delete()
        BookingTemplate.objects.filter(customer=customer, name='HTTP Test Template').delete()

        # Delete test bookings (cascades items, parties, audit logs)
        for b in created_bookings:
            b.delete()

        print(f'  Deleted {len(created_bookings)} test bookings + associated data')
        print('  Test data cleaned up.')

    # ── Summary ────────────────────────────────────────────────
    header('RESULTS')
    if all_pass:
        print('  All tests PASSED!')
    else:
        print('  Some tests FAILED — review output above.')
    print()


if __name__ == '__main__':
    main()
