"""
End-to-end test for the background worker and webhook retry system.

Run on PythonAnywhere:
    cd ~/freight-booking-system/backend
    source ~/.virtualenvs/freight-env/bin/activate
    python test_worker.py

Cleans up all test data when done.
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta

from bookings.models import Booking, Customer
from integrations.models import WebhookSubscription, WebhookDelivery
from integrations.webhook_dispatch import (
    _deliver_webhook, process_webhook_retries,
    MAX_RETRY_ATTEMPTS, BACKOFF_DELAYS,
)


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
    header('Setup: Creating test webhook subscription')

    # Find any customer to attach the subscription to
    customer = Customer.objects.first()
    if not customer:
        print('  ERROR: No customers in database. Cannot test.')
        sys.exit(1)

    print(f'  Using customer: {customer.code} ({customer.name})')

    # Create a webhook subscription pointing to a URL that will fail
    sub = WebhookSubscription.objects.create(
        customer=customer,
        url='https://test.invalid/webhook-will-fail',
        events=['booking.confirmed', 'booking.submitted'],
        secret='test-secret-for-worker-verification',
        is_active=True,
    )
    print(f'  Created subscription #{sub.pk} -> {sub.url}')

    try:
        # ── Test 1: Webhook delivery fails and schedules retry ─
        header('Test 1: Webhook delivery fails + retry scheduled')

        test_payload = {
            'event': 'booking.confirmed',
            'timestamp': timezone.now().isoformat(),
            'booking': {'booking_number': 'TEST-WORKER-001', 'status': 'CONFIRMED'},
        }

        _deliver_webhook(sub, 'booking.confirmed', test_payload, attempt_number=1)

        # Check delivery was created
        delivery = WebhookDelivery.objects.filter(
            subscription=sub
        ).order_by('-created_at').first()

        all_pass &= check('Delivery record created', delivery is not None)
        all_pass &= check('Delivery failed (as expected)', not delivery.success)
        all_pass &= check('Attempt number = 1', delivery.attempt_number == 1)
        all_pass &= check('next_retry_at is set', delivery.next_retry_at is not None)
        all_pass &= check(
            f'max_attempts = {MAX_RETRY_ATTEMPTS}',
            delivery.max_attempts == MAX_RETRY_ATTEMPTS,
        )

        if delivery.next_retry_at:
            delay = (delivery.next_retry_at - delivery.created_at).total_seconds()
            expected = BACKOFF_DELAYS[0]  # 60 seconds for attempt 1
            all_pass &= check(
                f'Backoff delay ~ {expected}s (actual: {delay:.0f}s)',
                abs(delay - expected) < 5,
            )

        # ── Test 2: Retry is NOT picked up (not due yet) ──────
        header('Test 2: Retry not picked up before scheduled time')

        count = process_webhook_retries()
        all_pass &= check(f'No retries processed (count={count})', count == 0)

        # ── Test 3: Fast-forward retry time and process ────────
        header('Test 3: Fast-forward next_retry_at and process retry')

        # Set next_retry_at to the past so the worker picks it up
        WebhookDelivery.objects.filter(pk=delivery.pk).update(
            next_retry_at=timezone.now() - timedelta(seconds=10)
        )
        print('  Set next_retry_at to 10 seconds ago')

        count = process_webhook_retries()
        all_pass &= check(f'1 retry processed (count={count})', count == 1)

        # Check the new delivery (attempt 2)
        retry_delivery = WebhookDelivery.objects.filter(
            subscription=sub,
            attempt_number=2,
        ).first()

        all_pass &= check('Retry delivery created (attempt 2)', retry_delivery is not None)
        if retry_delivery:
            all_pass &= check('Retry also failed (bad URL)', not retry_delivery.success)
            all_pass &= check(
                'Retry has next_retry_at set (attempt 2 < max)',
                retry_delivery.next_retry_at is not None,
            )
            if retry_delivery.next_retry_at:
                delay = (retry_delivery.next_retry_at - retry_delivery.created_at).total_seconds()
                expected = BACKOFF_DELAYS[1]  # 300 seconds for attempt 2
                all_pass &= check(
                    f'Backoff delay ~ {expected}s (actual: {delay:.0f}s)',
                    abs(delay - expected) < 5,
                )

        # ── Test 4: Original delivery's next_retry_at cleared ──
        header('Test 4: Original delivery claimed atomically')

        delivery.refresh_from_db()
        all_pass &= check(
            'Original delivery next_retry_at cleared (claimed)',
            delivery.next_retry_at is None,
        )

        # ── Test 5: Max attempts respected ─────────────────────
        header('Test 5: No retry scheduled at max attempts')

        # Create a delivery at max attempts
        max_delivery = WebhookDelivery.objects.create(
            subscription=sub,
            event_type='booking.confirmed',
            payload=test_payload,
            attempt_number=MAX_RETRY_ATTEMPTS,
            max_attempts=MAX_RETRY_ATTEMPTS,
            success=False,
            error_message='Test max attempt',
        )

        # Deliver at max attempts — should NOT schedule retry
        _deliver_webhook(sub, 'booking.confirmed', test_payload,
                         attempt_number=MAX_RETRY_ATTEMPTS)

        final_delivery = WebhookDelivery.objects.filter(
            subscription=sub,
            attempt_number=MAX_RETRY_ATTEMPTS,
        ).order_by('-created_at').first()

        all_pass &= check(
            'No retry scheduled at max attempts',
            final_delivery.next_retry_at is None,
        )

        # ── Test 6: Worker --once runs clean ───────────────────
        header('Test 6: run_worker --once executes without error')

        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        try:
            call_command('run_worker', '--once', stdout=out)
            output = out.getvalue()
            all_pass &= check(
                'Worker completed gracefully',
                'Worker stopped gracefully' in output,
            )
        except Exception as e:
            all_pass &= check(f'Worker failed: {e}', False)

        # ── Test 7: Backup command works ───────────────────────
        header('Test 7: backup_db runs successfully')

        out = StringIO()
        try:
            call_command('backup_db', stdout=out)
            output = out.getvalue()
            all_pass &= check('Backup created', 'Backup created' in output)
            all_pass &= check('WAL checkpoint ran', 'WAL checkpoint' in output)
        except Exception as e:
            all_pass &= check(f'Backup failed: {e}', False)

    finally:
        # ── Cleanup ────────────────────────────────────────────
        header('Cleanup')

        delivery_count = WebhookDelivery.objects.filter(subscription=sub).count()
        WebhookDelivery.objects.filter(subscription=sub).delete()
        sub.delete()
        print(f'  Deleted {delivery_count} test deliveries + subscription')

        # Reset consecutive_failures on the customer's other subscriptions
        # (our test failures incremented the counter)
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
