"""
Notification service for booking status transitions.

Sends both email and in-app notifications. Each function collects active
user emails for the booking's customer, renders an HTML email, and creates
in-app Notification records.

Dev uses console backend; production: set DJANGO_EMAIL_BACKEND env var.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import UserProfile, Notification

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


def _create_customer_notifications(booking, notification_type, message):
    """Create in-app notifications for all active users of the booking's customer."""
    profiles = UserProfile.objects.filter(
        customer=booking.customer,
        user__is_active=True,
    ).select_related('user')
    notifications = [
        Notification(
            user=p.user,
            booking=booking,
            message=message,
            notification_type=notification_type,
        )
        for p in profiles
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def _create_staff_notifications(booking, notification_type, message):
    """Create in-app notifications for all active staff users (no customer)."""
    staff_profiles = UserProfile.objects.filter(
        customer__isnull=True,
        user__is_active=True,
    ).select_related('user')
    notifications = [
        Notification(
            user=p.user,
            booking=booking,
            message=message,
            notification_type=notification_type,
        )
        for p in staff_profiles
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def notify_booking_submitted(booking):
    """Notify customer that their booking has been submitted for review."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Submitted',
        template_name='bookings/emails/booking_submitted.html',
        context={'booking': booking},
        recipient_list=emails,
    )
    _create_customer_notifications(
        booking, 'BOOKING_SUBMITTED',
        f'Booking {booking.booking_number} has been submitted for review.',
    )
    _create_staff_notifications(
        booking, 'BOOKING_SUBMITTED',
        f'New booking {booking.booking_number} from {booking.customer.name} awaiting review.',
    )


def notify_booking_confirmed(booking):
    """Notify customer that their booking has been confirmed."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Confirmed',
        template_name='bookings/emails/booking_confirmed.html',
        context={'booking': booking},
        recipient_list=emails,
    )
    _create_customer_notifications(
        booking, 'BOOKING_CONFIRMED',
        f'Booking {booking.booking_number} has been confirmed.',
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
    _create_customer_notifications(
        booking, 'BOOKING_REJECTED',
        f'Booking {booking.booking_number} has been rejected. Please review and resubmit.',
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
    _create_customer_notifications(
        booking, 'BOOKING_IN_TRANSIT',
        f'Booking {booking.booking_number} is now in transit.',
    )


def notify_booking_arrived(booking):
    """Notify customer that their cargo has arrived at destination."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Arrived at Destination',
        template_name='bookings/emails/booking_arrived.html',
        context={'booking': booking},
        recipient_list=emails,
    )
    _create_customer_notifications(
        booking, 'BOOKING_ARRIVED',
        f'Booking {booking.booking_number} has arrived at destination.',
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
    _create_customer_notifications(
        booking, 'BOOKING_COMPLETED',
        f'Booking {booking.booking_number} has been completed.',
    )


def notify_booking_cancelled(booking):
    """Notify customer that their booking has been cancelled."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} Cancelled',
        template_name='bookings/emails/booking_cancelled.html',
        context={'booking': booking},
        recipient_list=emails,
    )
    _create_customer_notifications(
        booking, 'BOOKING_CANCELLED',
        f'Booking {booking.booking_number} has been cancelled.',
    )


def notify_booking_customer_approved(booking):
    """Notify staff that the customer has approved the confirmed booking."""
    _create_staff_notifications(
        booking, 'BOOKING_CUSTOMER_APPROVED',
        f'Customer approved booking {booking.booking_number} — ready for packing.',
    )


def notify_booking_customer_rejected(booking):
    """Notify staff that the customer has rejected the confirmed booking."""
    _create_staff_notifications(
        booking, 'BOOKING_CUSTOMER_REJECTED',
        f'Customer rejected booking {booking.booking_number}. Reason: '
        f'{booking.customer_rejection_reason[:100]}',
    )


def notify_booking_resubmitted(booking):
    """Notify customer that their rejected booking is back in draft for revision."""
    emails = _get_customer_emails(booking)
    _send_notification(
        subject=f'Booking {booking.booking_number} — Ready for Revision',
        template_name='bookings/emails/booking_resubmitted.html',
        context={'booking': booking},
        recipient_list=emails,
    )
    _create_customer_notifications(
        booking, 'BOOKING_RESUBMITTED',
        f'Booking {booking.booking_number} has been returned to draft for revision.',
    )
