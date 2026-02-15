"""
Outbound webhook dispatch — delivers booking events to subscriber URLs.

Uses HMAC-SHA256 for payload signing. Failed deliveries are retried with
exponential backoff (1min → 5min → 15min → 1hr → 2hr).
"""
import hashlib
import hmac
import json
import logging
from datetime import timedelta

import requests
from django.db.models import F, Q
from django.utils import timezone

from .models import WebhookSubscription, WebhookDelivery

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
MAX_RETRY_ATTEMPTS = 5
BACKOFF_DELAYS = [60, 300, 900, 3600, 7200]  # seconds: 1m, 5m, 15m, 1h, 2h


def compute_signature(payload_bytes, secret):
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def dispatch_webhook_event(booking, event_type):
    """
    Send a webhook event to all matching subscribers for the booking's customer.

    Called from Django signals after BookingService state transitions.
    """
    subscriptions = WebhookSubscription.objects.filter(
        customer=booking.customer,
        is_active=True,
    )

    # Fetch booking once with all relations (not per-subscription)
    from bookings.serializers import BookingDetailSerializer
    from bookings.models import Booking

    fresh_booking = Booking.objects.select_related(
        'customer', 'origin_port', 'destination_port',
        'container_type', 'carrier_config',
    ).prefetch_related(
        'items', 'booking_parties', 'documents',
    ).get(pk=booking.pk)

    booking_data = BookingDetailSerializer(fresh_booking).data

    for sub in subscriptions:
        if event_type not in sub.events:
            continue

        payload = {
            'event': event_type,
            'timestamp': timezone.now().isoformat(),
            'booking': booking_data,
        }

        _deliver_webhook(sub, event_type, payload)


def _deliver_webhook(subscription, event_type, payload, attempt_number=1):
    """Attempt to deliver a webhook payload with retry scheduling on failure."""
    payload_bytes = json.dumps(payload, default=str).encode('utf-8')
    signature = compute_signature(payload_bytes, subscription.secret)

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Signature': f'sha256={signature}',
        'X-Webhook-Event': event_type,
        'User-Agent': 'FreightBooking-Webhook/1.0',
    }

    delivery = WebhookDelivery(
        subscription=subscription,
        event_type=event_type,
        payload=payload,
        attempt_number=attempt_number,
        max_attempts=MAX_RETRY_ATTEMPTS,
    )

    try:
        response = requests.post(
            subscription.url,
            data=payload_bytes,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        delivery.response_status = response.status_code
        delivery.response_body = response.text[:2000]
        delivery.success = response.status_code in (200, 201, 202, 204)
    except requests.RequestException as e:
        delivery.error_message = str(e)[:2000]
        delivery.success = False

    # Schedule retry on failure if under max attempts
    if not delivery.success and attempt_number < MAX_RETRY_ATTEMPTS:
        delay_idx = min(attempt_number - 1, len(BACKOFF_DELAYS) - 1)
        delivery.next_retry_at = timezone.now() + timedelta(
            seconds=BACKOFF_DELAYS[delay_idx]
        )

    delivery.save()

    if delivery.success:
        subscription.last_delivery_at = timezone.now()
        subscription.consecutive_failures = 0
        subscription.save(
            update_fields=['last_delivery_at', 'consecutive_failures'],
        )
    else:
        # Atomic increment to avoid race conditions
        WebhookSubscription.objects.filter(pk=subscription.pk).update(
            consecutive_failures=F('consecutive_failures') + 1,
        )
        subscription.refresh_from_db()

        # Auto-disable after 10 consecutive failures
        if subscription.consecutive_failures >= 10:
            subscription.is_active = False
            subscription.save(update_fields=['is_active'])
            # Clear all pending retries for this subscription
            WebhookDelivery.objects.filter(
                subscription=subscription,
                success=False,
                next_retry_at__isnull=False,
            ).update(next_retry_at=None)
            logger.warning(
                'Webhook %s auto-disabled after %d failures — pending retries cleared',
                subscription.url, subscription.consecutive_failures,
            )
        else:
            retry_info = ''
            if delivery.next_retry_at:
                retry_info = f', retry at {delivery.next_retry_at:%H:%M:%S}'
            logger.info(
                'Webhook delivery to %s failed (attempt %d/%d, failures: %d%s)',
                subscription.url, attempt_number, MAX_RETRY_ATTEMPTS,
                subscription.consecutive_failures, retry_info,
            )


def process_webhook_retries():
    """Process pending webhook retries. Called by the background worker.

    Returns the number of retries processed.
    """
    now = timezone.now()
    pending = WebhookDelivery.objects.filter(
        success=False,
        next_retry_at__lte=now,
        subscription__is_active=True,
    ).select_related('subscription').order_by('next_retry_at')[:50]

    count = 0
    for delivery in pending:
        # Atomically claim by clearing next_retry_at — prevents duplicate retries
        claimed = WebhookDelivery.objects.filter(
            pk=delivery.pk,
            next_retry_at__isnull=False,
        ).update(next_retry_at=None)
        if not claimed:
            continue

        next_attempt = delivery.attempt_number + 1
        _deliver_webhook(
            delivery.subscription,
            delivery.event_type,
            delivery.payload,
            attempt_number=next_attempt,
        )
        count += 1

    if count:
        logger.info('Processed %d webhook retries', count)
    return count
