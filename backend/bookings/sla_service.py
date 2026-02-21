"""SLA timer checking and escalation service."""

import logging

from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

# Status → timestamp field mapping for "when did booking enter this status"
STATUS_TIMESTAMP_MAP = {
    'SUBMITTED': 'submitted_at',
    'CONFIRMED': 'confirmed_at',
    'PACKING': 'confirmed_at',  # packing starts after confirm
    'IN_TRANSIT': 'in_transit_at',
    'ARRIVED': 'arrived_at',
}


def _get_status_entered_at(booking):
    """Get the timestamp when the booking entered its current status."""
    field = STATUS_TIMESTAMP_MAP.get(booking.status)
    if field:
        return getattr(booking, field, None)
    return None


def get_sla_status(booking):
    """Get SLA status for a booking.

    Returns dict: {
        'has_sla': bool,
        'max_hours': int or None,
        'elapsed_hours': float or None,
        'remaining_hours': float or None,
        'status': 'OK' | 'WARNING' | 'BREACHED',
        'pct': float (0-100+),
    }
    """
    from .models import SLAConfig

    org = booking.customer.organization
    try:
        sla = SLAConfig.objects.get(
            organization=org, status=booking.status, is_active=True)
    except SLAConfig.DoesNotExist:
        return {'has_sla': False}

    entered_at = _get_status_entered_at(booking)
    if not entered_at:
        return {'has_sla': False}

    now = timezone.now()
    elapsed = (now - entered_at).total_seconds() / 3600
    remaining = sla.max_hours - elapsed
    pct = (elapsed / sla.max_hours) * 100 if sla.max_hours else 0

    if elapsed >= sla.max_hours:
        status = 'BREACHED'
    elif pct >= sla.warning_pct:
        status = 'WARNING'
    else:
        status = 'OK'

    return {
        'has_sla': True,
        'max_hours': sla.max_hours,
        'elapsed_hours': round(elapsed, 1),
        'remaining_hours': round(max(remaining, 0), 1),
        'status': status,
        'pct': round(pct, 1),
    }


def check_sla_breaches():
    """Scan all active bookings for SLA breaches.

    Creates SLABreach records and sends escalation notifications.
    Returns (breaches_found, errors).
    """
    from .models import Booking, SLAConfig, SLABreach

    active_statuses = list(STATUS_TIMESTAMP_MAP.keys())
    configs = SLAConfig.objects.filter(
        is_active=True, status__in=active_statuses
    ).select_related('organization')

    breaches_found = 0
    errors = []

    for config in configs:
        bookings = Booking.objects.filter(
            customer__organization=config.organization,
            status=config.status,
        ).exclude(
            status__in=['COMPLETED', 'CANCELLED', 'REJECTED']
        )

        now = timezone.now()

        for booking in bookings:
            entered_at = _get_status_entered_at(booking)
            if not entered_at:
                continue

            elapsed_hours = (now - entered_at).total_seconds() / 3600
            if elapsed_hours < config.max_hours:
                continue

            # Check if breach already recorded
            existing = SLABreach.objects.filter(
                booking=booking, sla_config=config, resolved_at__isnull=True
            ).exists()
            if existing:
                continue

            # Create breach record
            breach = SLABreach.objects.create(
                booking=booking,
                sla_config=config,
                status=config.status,
                entered_at=entered_at,
                breached_at=now,
            )
            breaches_found += 1

            # Escalate
            try:
                _escalate_breach(breach, config)
            except Exception as e:
                errors.append(f'{booking.booking_number}: {e}')

    return breaches_found, errors


def _escalate_breach(breach, config):
    """Send escalation for an SLA breach."""
    if config.escalation_action in ('NOTIFY', 'BOTH') and config.escalation_email:
        subject = f'SLA Breach: {breach.booking.booking_number} - {breach.status}'
        message = (
            f'Booking {breach.booking.booking_number} has breached its SLA.\n\n'
            f'Status: {breach.status}\n'
            f'Max allowed: {config.max_hours} hours\n'
            f'Entered status at: {breach.entered_at}\n'
            f'Customer: {breach.booking.customer.name}\n'
        )
        send_mail(
            subject, message,
            None,  # uses DEFAULT_FROM_EMAIL
            [config.escalation_email],
            fail_silently=True,
        )
        breach.escalated = True
        breach.save(update_fields=['escalated'])

    # Phone notification for SLA breach
    from .sms_service import notify_booking_event_via_phone
    notify_booking_event_via_phone(breach.booking, 'SLA_BREACH')


def resolve_breach(booking):
    """Mark any open SLA breaches as resolved when booking moves to next status."""
    from .models import SLABreach
    SLABreach.objects.filter(
        booking=booking, resolved_at__isnull=True
    ).update(resolved_at=timezone.now())
