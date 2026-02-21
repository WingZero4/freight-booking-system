"""WhatsApp and SMS notification service via Twilio."""

import logging
import os

logger = logging.getLogger(__name__)

# Twilio credentials from environment
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')

# Critical events that warrant phone notifications
PHONE_EVENTS = {
    'BOOKING_IN_TRANSIT', 'BOOKING_ARRIVED', 'BOOKING_COMPLETED',
    'BOOKING_OPTIONS_PRESENTED', 'SLA_BREACH',
}


def _get_twilio_client():
    """Get Twilio client, or None if not configured."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        return None
    try:
        from twilio.rest import Client
        return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except ImportError:
        logger.warning('twilio package not installed')
        return None


def send_sms(phone, message):
    """Send an SMS via Twilio. Returns True on success."""
    client = _get_twilio_client()
    if not client or not TWILIO_PHONE_NUMBER:
        logger.info('SMS not configured, skipping: %s', phone)
        return False
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=phone,
        )
        return True
    except Exception as e:
        logger.error('SMS send failed to %s: %s', phone, e)
        return False


def send_whatsapp(phone, message):
    """Send a WhatsApp message via Twilio. Returns True on success."""
    client = _get_twilio_client()
    if not client or not TWILIO_WHATSAPP_NUMBER:
        logger.info('WhatsApp not configured, skipping: %s', phone)
        return False
    try:
        client.messages.create(
            body=message,
            from_=f'whatsapp:{TWILIO_WHATSAPP_NUMBER}',
            to=f'whatsapp:{phone}',
        )
        return True
    except Exception as e:
        logger.error('WhatsApp send failed to %s: %s', phone, e)
        return False


def notify_via_phone(user, booking, event_type):
    """Send phone notification to a user for a booking event.

    Checks user preferences and sends via preferred channel.
    Only sends for critical events defined in PHONE_EVENTS.
    """
    if event_type not in PHONE_EVENTS:
        return

    try:
        profile = user.profile
    except Exception:
        return

    if not profile.phone:
        return

    phone = profile.phone

    # Build short message
    msg = _build_message(booking, event_type)
    if not msg:
        return

    # Prefer WhatsApp over SMS
    if profile.whatsapp_notifications:
        send_whatsapp(phone, msg)
    elif profile.phone_notifications:
        send_sms(phone, msg)


def _build_message(booking, event_type):
    """Build a short notification message for SMS/WhatsApp."""
    bn = booking.booking_number
    messages = {
        'BOOKING_IN_TRANSIT': f'{bn} is now IN TRANSIT. ETA: {booking.eta or "TBD"}',
        'BOOKING_ARRIVED': f'{bn} has ARRIVED at destination.',
        'BOOKING_COMPLETED': f'{bn} is now COMPLETED.',
        'BOOKING_OPTIONS_PRESENTED': f'{bn} has carrier options ready for your review.',
        'SLA_BREACH': f'SLA BREACH: {bn} has exceeded its time limit.',
    }
    return messages.get(event_type)


def notify_booking_event_via_phone(booking, event_type):
    """Send phone notifications to all relevant users for a booking event.

    Sends to customer users of the booking's customer.
    """
    from .feature_service import FeatureFlagService

    org = booking.customer.organization
    if not FeatureFlagService.is_enabled(org, 'enable_phone_notifications'):
        return

    from django.db import models as db_models
    from .models import UserProfile
    profiles = UserProfile.objects.filter(
        customer=booking.customer,
        approval_status='APPROVED',
    ).filter(
        db_models.Q(phone_notifications=True) | db_models.Q(whatsapp_notifications=True)
    ).select_related('user')

    for profile in profiles:
        notify_via_phone(profile.user, booking, event_type)
