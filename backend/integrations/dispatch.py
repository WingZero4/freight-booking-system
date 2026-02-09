"""
Integration dispatch — routes booking events to the correct FMS adapter.

Called from BookingService after status transitions. If a customer has
no IntegrationConfig, all dispatch calls are no-ops.
"""
import logging

from .models import IntegrationConfig, IntegrationLog
from .adapters.webhook import WebhookAdapter
from .adapters.cargowise import CargoWiseAdapter

logger = logging.getLogger(__name__)

# Registry of adapter classes by adapter_type key
ADAPTER_REGISTRY = {
    'webhook': WebhookAdapter,
    'cargowise': CargoWiseAdapter,
}


def _get_config(booking):
    """Get active IntegrationConfig for the booking's customer, or None."""
    try:
        config = IntegrationConfig.objects.select_related('customer').get(
            customer=booking.customer,
            is_active=True,
        )
        return config
    except IntegrationConfig.DoesNotExist:
        return None


def _get_adapter(config):
    """Instantiate the correct adapter for the given config, or None."""
    adapter_cls = ADAPTER_REGISTRY.get(config.adapter_type)
    if adapter_cls is None:
        logger.error(
            'Adapter type "%s" not implemented for customer %s',
            config.adapter_type, config.customer.code,
        )
        return None
    return adapter_cls(config)


def _serialize_booking(booking):
    """Serialize booking to canonical JSON using DRF serializer."""
    from bookings.models import Booking
    from bookings.serializers import BookingDetailSerializer

    # Re-fetch with all relations to avoid N+1 queries
    booking = Booking.objects.select_related(
        'customer', 'origin_port', 'destination_port', 'container_type',
    ).prefetch_related(
        'items', 'booking_parties', 'documents',
    ).get(pk=booking.pk)

    serializer = BookingDetailSerializer(booking)
    return serializer.data


def _log_result(booking, config, event, result, request_payload=None):
    """Create an IntegrationLog entry for the result."""
    IntegrationLog.objects.create(
        booking=booking,
        config=config,
        event=event,
        adapter_type=config.adapter_type if config else '',
        request_payload=request_payload,
        response_payload=result.response_data,
        http_status=result.http_status,
        error_message=result.error_message,
    )


def _update_booking_fms_status(booking, result):
    """Update the booking's FMS push status and reference numbers."""
    fields_to_update = ['fms_push_status', 'fms_push_error', 'updated_at']

    if result.success:
        booking.fms_push_status = 'PUSHED'
        booking.fms_push_error = ''
        # Store any reference numbers from the FMS response
        for field, value in result.references.items():
            if hasattr(booking, field) and value:
                setattr(booking, field, value)
                fields_to_update.append(field)
    else:
        booking.fms_push_status = 'FAILED'
        booking.fms_push_error = result.error_message[:1000]

    # Avoid overwriting a callback that arrived before this save
    from bookings.models import Booking
    Booking.objects.filter(
        pk=booking.pk
    ).exclude(
        fms_push_status='CALLBACK_RECEIVED'
    ).update(**{f: getattr(booking, f) for f in fields_to_update if f != 'updated_at'})


def dispatch_booking_confirmed(booking):
    """
    Push a confirmed booking to the customer's FMS.

    Called from BookingService.confirm_booking(). No-op if the customer
    has no active integration config or auto_push_on_confirm is False.
    """
    config = _get_config(booking)
    if config is None:
        return  # No integration configured — no-op

    if not config.auto_push_on_confirm:
        logger.info(
            'Auto-push disabled for %s — skipping FMS push',
            booking.booking_number,
        )
        return

    adapter = _get_adapter(config)
    if adapter is None:
        # Adapter type not implemented — mark as failed
        from bookings.models import Booking
        Booking.objects.filter(pk=booking.pk).update(
            fms_push_status='FAILED',
            fms_push_error=f'Adapter "{config.adapter_type}" not implemented',
        )
        return

    # Mark as pending
    booking.fms_push_status = 'PENDING'
    booking.save(update_fields=['fms_push_status', 'updated_at'])

    canonical = _serialize_booking(booking)

    logger.info(
        'Pushing %s to %s (%s)',
        booking.booking_number, config.adapter_type, config.api_endpoint,
    )

    result = adapter.push_booking(canonical)

    _log_result(booking, config, 'PUSH_SUCCESS' if result.success else 'PUSH_FAILED',
                result, request_payload=canonical)
    _update_booking_fms_status(booking, result)

    if result.success:
        logger.info('FMS push successful for %s', booking.booking_number)
    else:
        logger.warning(
            'FMS push failed for %s: %s',
            booking.booking_number, result.error_message,
        )


def dispatch_milestone_update(booking, milestone_type):
    """
    Send a milestone update to the FMS (IN_TRANSIT or COMPLETED).

    Called from BookingService.mark_in_transit() and complete_booking().
    """
    config = _get_config(booking)
    if config is None:
        return

    adapter = _get_adapter(config)
    if adapter is None:
        return

    canonical = _serialize_booking(booking)

    logger.info(
        'Sending %s milestone for %s to %s',
        milestone_type, booking.booking_number, config.adapter_type,
    )

    result = adapter.update_milestone(canonical, milestone_type)
    _log_result(booking, config, 'UPDATE', result, request_payload=canonical)


def dispatch_cancellation(booking):
    """
    Notify the FMS that a booking has been cancelled.

    Called from BookingService.cancel_booking() when the booking
    was previously pushed to the FMS (fms_push_status != '').
    """
    config = _get_config(booking)
    if config is None:
        return

    # Only send cancellation if the FMS actually has this booking
    if booking.fms_push_status not in ('PUSHED', 'CALLBACK_RECEIVED'):
        return

    adapter = _get_adapter(config)
    if adapter is None:
        return

    canonical = _serialize_booking(booking)

    logger.info(
        'Sending cancellation for %s to %s',
        booking.booking_number, config.adapter_type,
    )

    result = adapter.cancel_shipment(canonical)
    _log_result(booking, config, 'CANCEL', result, request_payload=canonical)
