"""
Django signals for booking events.

Hooks into AuditLog post_save to dispatch webhook events.
Uses transaction.on_commit to ensure webhooks fire only after DB commit.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AuditLog

logger = logging.getLogger(__name__)

# Map AuditLog actions to webhook event types
ACTION_TO_EVENT = {
    'CREATED': 'booking.created',
    'SUBMITTED': 'booking.submitted',
    'CONFIRMED': 'booking.confirmed',
    'REJECTED': 'booking.rejected',
    'IN_TRANSIT': 'booking.in_transit',
    'COMPLETED': 'booking.completed',
    'CANCELLED': 'booking.cancelled',
}


@receiver(post_save, sender=AuditLog)
def dispatch_webhook_on_audit_log(sender, instance, created, **kwargs):
    """When an AuditLog is created, dispatch matching webhook events after commit."""
    if not created:
        return

    event_type = ACTION_TO_EVENT.get(instance.action)
    if not event_type:
        return

    booking_id = instance.booking_id

    def _dispatch():
        try:
            from integrations.webhook_dispatch import dispatch_webhook_event
            from .models import Booking
            booking = Booking.objects.get(pk=booking_id)
            dispatch_webhook_event(booking, event_type)
        except Exception:
            logger.exception(
                'Webhook dispatch failed for %s event on booking %s',
                event_type, booking_id,
            )

    transaction.on_commit(_dispatch)
