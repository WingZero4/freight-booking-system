"""
Outbound webhook dispatch — delivers booking events to subscriber URLs.

Uses HMAC-SHA256 for payload signing. Logs failures for later retry.
"""
import hashlib
import hmac
import json
import logging

import requests
from django.db.models import F
from django.utils import timezone

from .models import WebhookSubscription, WebhookDelivery

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10


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


def _deliver_webhook(subscription, event_type, payload):
    """Attempt to deliver a webhook payload (single attempt, no blocking retry)."""
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
        attempt_number=1,
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
            logger.warning(
                'Webhook %s auto-disabled after %d failures',
                subscription.url, subscription.consecutive_failures,
            )
        else:
            logger.info(
                'Webhook delivery to %s failed (failures: %d)',
                subscription.url, subscription.consecutive_failures,
            )
