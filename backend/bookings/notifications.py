"""
Email notification service for booking status transitions.

Each function collects active user emails for the booking's customer,
renders an HTML email, and sends via Django's mail framework.

Dev uses console backend; production: set DJANGO_EMAIL_BACKEND env var.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import UserProfile

logger = logging.getLogger(__name__)


def _get_customer_emails(booking):
    """Return list of email addresses for all active users of the booking's customer."""
    profiles = UserProfile.objects.filter(
        customer=booking.customer,
        user__is_active=True,
    ).select_related('user')
    return [p.user.email for p in profiles if p.user.email]


def _send_notification(subject, template_name, context, recipient_list):
    """Render template and send email, failing silently."""
    if not recipient_list:
        logger.info('No recipients for notification: %s', subject)
        return

    html_body = render_to_string(template_name, context)

    try:
        send_mail(
            subject=subject,
            message='',  # plain-text fallback (empty — HTML only)
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_body,
            fail_silently=True,
        )
    except Exception:
        logger.exception('Failed to send notification: %s', subject)


def notify_booking_confirmed(booking):
    """Notify customer that their booking has been confirmed."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Confirmed',
        template_name='bookings/emails/booking_confirmed.html',
        context={'booking': booking},
        recipient_list=emails,
    )


def notify_booking_rejected(booking):
    """Notify customer that their booking has been rejected."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Rejected',
        template_name='bookings/emails/booking_rejected.html',
        context={'booking': booking},
        recipient_list=emails,
    )


def notify_booking_in_transit(booking):
    """Notify customer that their booking is now in transit."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} In Transit',
        template_name='bookings/emails/booking_in_transit.html',
        context={'booking': booking},
        recipient_list=emails,
    )


def notify_booking_completed(booking):
    """Notify customer that their booking has been completed."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Completed',
        template_name='bookings/emails/booking_completed.html',
        context={'booking': booking},
        recipient_list=emails,
    )
