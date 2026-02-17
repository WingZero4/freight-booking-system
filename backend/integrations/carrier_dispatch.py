"""
Carrier integration dispatch — routes booking events to carrier APIs.

This is the carrier-side counterpart to dispatch.py (which handles FMS push).
Called from BookingService after confirm or when ops triggers carrier submission.

Flow:
  1. BookingService.confirm_booking() or explicit carrier request
  2. dispatch_carrier_booking(booking) — sends to carrier API
  3. Carrier responds (sync or async callback)
  4. process_carrier_callback(booking, data) — processes response
  5. If auto_chain_to_fms: triggers dispatch.dispatch_booking_confirmed()
"""
import logging

from .models import CarrierConfig, IntegrationLog
from .adapters.carrier_webhook import CarrierWebhookAdapter
from .adapters.dcsa_booking import DCSABookingAdapter
from .adapters.iata_one_record import IATAOneRecordAdapter
from .adapters.maersk import MaerskAdapter

logger = logging.getLogger(__name__)

CARRIER_ADAPTER_REGISTRY = {
    'carrier_webhook': CarrierWebhookAdapter,
    'dcsa': DCSABookingAdapter,
    'one_record': IATAOneRecordAdapter,
    'maersk': MaerskAdapter,
}


def _get_carrier_config(booking):
    """Get active CarrierConfig for the booking, or None."""
    if not booking.carrier_config_id:
        return None
    try:
        return CarrierConfig.objects.get(
            pk=booking.carrier_config_id, is_active=True
        )
    except CarrierConfig.DoesNotExist:
        return None


def _get_carrier_adapter(config):
    """Instantiate the correct carrier adapter, or None."""
    adapter_cls = CARRIER_ADAPTER_REGISTRY.get(config.adapter_type)
    if adapter_cls is None:
        logger.error(
            'Carrier adapter "%s" not implemented for %s',
            config.adapter_type, config.carrier_code,
        )
        return None
    return adapter_cls(config)


def _serialize_booking(booking):
    """Serialize booking to canonical JSON (reuses FMS serializer)."""
    from bookings.models import Booking
    from bookings.serializers import BookingDetailSerializer

    booking = Booking.objects.select_related(
        'customer', 'origin_port', 'destination_port', 'container_type',
        'carrier_config',
    ).prefetch_related(
        'items', 'booking_parties', 'documents',
    ).get(pk=booking.pk)

    serializer = BookingDetailSerializer(booking)
    return serializer.data


def _log_carrier_result(booking, carrier_config, event, result,
                        request_payload=None):
    """Create an IntegrationLog entry for a carrier event."""
    IntegrationLog.objects.create(
        booking=booking,
        carrier_config=carrier_config,
        event=event,
        adapter_type=carrier_config.adapter_type if carrier_config else '',
        request_payload=request_payload,
        response_payload=getattr(result, 'response_data', None),
        http_status=getattr(result, 'http_status', None),
        error_message=getattr(result, 'error_message', ''),
    )


def _update_carrier_status(booking, result, status_on_success='SUBMITTED'):
    """Update booking carrier request status fields."""
    from bookings.models import Booking

    fields_to_update = {
        'carrier_request_status': status_on_success if result.success else 'FAILED',
        'carrier_request_error': '' if result.success else result.error_message[:1000],
    }

    # Store any synchronous references (initial ref → carrier_booking_ref)
    if result.success:
        refs = result.references or {}
        if refs.get('carrier_booking_ref'):
            fields_to_update['carrier_booking_ref'] = refs['carrier_booking_ref']

    Booking.objects.filter(pk=booking.pk).update(**fields_to_update)


# ─── Public dispatch functions ──────────────────────────────────────


def dispatch_carrier_booking(booking):
    """
    Submit a booking request to the carrier API.

    Called from BookingService.confirm_booking() or explicitly by ops.
    No-op if booking has no carrier_config assigned.
    """
    carrier_config = _get_carrier_config(booking)
    if carrier_config is None:
        logger.debug(
            'No carrier config for %s — skipping carrier dispatch',
            booking.booking_number,
        )
        return

    adapter = _get_carrier_adapter(carrier_config)
    if adapter is None:
        from bookings.models import Booking
        Booking.objects.filter(pk=booking.pk).update(
            carrier_request_status='FAILED',
            carrier_request_error=(
                f'Carrier adapter "{carrier_config.adapter_type}" not implemented'
            ),
        )
        return

    # Mark as pending
    from bookings.models import Booking
    Booking.objects.filter(pk=booking.pk).update(
        carrier_request_status='PENDING',
    )

    canonical = _serialize_booking(booking)

    logger.info(
        'Submitting carrier booking for %s to %s (%s)',
        booking.booking_number, carrier_config.carrier_code,
        carrier_config.api_endpoint,
    )

    result = adapter.submit_booking(canonical)

    event = 'CARRIER_SUCCESS' if result.success else 'CARRIER_FAILED'
    _log_carrier_result(
        booking, carrier_config, event, result, request_payload=canonical
    )
    _update_carrier_status(booking, result, status_on_success='SUBMITTED')

    # If carrier responds synchronously with confirmation
    if result.success and not carrier_config.supports_async_callback:
        _handle_confirmed(booking, carrier_config, result.references or {})

    if result.success:
        logger.info('Carrier submission accepted for %s', booking.booking_number)
    else:
        logger.warning(
            'Carrier submission failed for %s: %s',
            booking.booking_number, result.error_message,
        )


def process_carrier_callback(booking, callback_data):
    """
    Process a carrier callback (async confirmation/rejection).

    Called from the carrier callback API endpoint.
    """
    carrier_config = _get_carrier_config(booking)
    if carrier_config is None:
        logger.warning(
            'Carrier callback for %s but no carrier config found',
            booking.booking_number,
        )
        return

    adapter = _get_carrier_adapter(carrier_config)

    # Normalize the callback payload
    if adapter and hasattr(adapter, 'parse_callback'):
        normalized = adapter.parse_callback(callback_data)
    else:
        normalized = callback_data

    callback_status = normalized.get('status', '')

    # Log the callback
    from .adapters.base import AdapterResult
    log_result = AdapterResult(
        success=(callback_status == 'CONFIRMED'),
        response_data=callback_data,
        error_message=normalized.get('message', ''),
    )
    _log_carrier_result(booking, carrier_config, 'CARRIER_CALLBACK', log_result)

    if callback_status == 'CONFIRMED':
        _handle_confirmed(booking, carrier_config, normalized)
    elif callback_status == 'REJECTED':
        _handle_rejected(booking, carrier_config, normalized)
    elif callback_status == 'AMENDMENT_REQUIRED':
        _handle_amendment_required(booking, carrier_config, normalized)
    else:
        logger.warning(
            'Unknown carrier callback status "%s" for %s',
            callback_status, booking.booking_number,
        )


def dispatch_carrier_cancellation(booking):
    """
    Send a cancellation to the carrier for a previously submitted booking.

    Called from BookingService.cancel_booking() when carrier_request_status
    is SUBMITTED or CONFIRMED.
    """
    carrier_config = _get_carrier_config(booking)
    if carrier_config is None:
        return

    if booking.carrier_request_status not in ('SUBMITTED', 'CONFIRMED'):
        return

    adapter = _get_carrier_adapter(carrier_config)
    if adapter is None:
        return

    canonical = _serialize_booking(booking)
    carrier_ref = (
        booking.carrier_confirmation_ref or booking.carrier_booking_ref
    )

    logger.info(
        'Sending carrier cancellation for %s to %s',
        booking.booking_number, carrier_config.carrier_code,
    )

    result = adapter.cancel_booking(canonical, carrier_ref)
    _log_carrier_result(
        booking, carrier_config, 'CARRIER_CANCEL', result,
        request_payload=canonical,
    )

    if result.success:
        from bookings.models import Booking
        Booking.objects.filter(pk=booking.pk).update(
            carrier_request_status='CANCELLED',
        )


# ─── Internal helpers ───────────────────────────────────────────────


def _handle_confirmed(booking, carrier_config, data):
    """Handle carrier confirmation: populate fields, optionally chain to FMS."""
    from bookings.models import Booking

    update_fields = {
        'carrier_request_status': 'CONFIRMED',
        'carrier_request_error': '',
    }

    if data.get('carrier_booking_ref'):
        update_fields['carrier_booking_ref'] = data['carrier_booking_ref']
        update_fields['carrier_confirmation_ref'] = data['carrier_booking_ref']
    if data.get('vessel_name'):
        update_fields['vessel_name'] = data['vessel_name']
    if data.get('voyage_number'):
        update_fields['voyage_number'] = data['voyage_number']
    if data.get('etd'):
        update_fields['etd'] = data['etd']
    if data.get('eta'):
        update_fields['eta'] = data['eta']
    if data.get('container_numbers'):
        if isinstance(data['container_numbers'], list):
            update_fields['container_numbers'] = '\n'.join(
                data['container_numbers']
            )
        else:
            update_fields['container_numbers'] = data['container_numbers']

    # Set carrier_name from config if not already set
    if not booking.carrier_name and carrier_config:
        update_fields['carrier_name'] = carrier_config.carrier_name

    Booking.objects.filter(pk=booking.pk).update(**update_fields)
    booking.refresh_from_db()

    # Log confirmation
    from .adapters.base import AdapterResult
    log_result = AdapterResult(
        success=True,
        response_data=data,
    )
    _log_carrier_result(booking, carrier_config, 'CARRIER_CONFIRMED', log_result)

    logger.info(
        'Carrier confirmed booking %s (ref: %s)',
        booking.booking_number,
        data.get('carrier_booking_ref', 'N/A'),
    )

    # Chain to FMS push if configured
    if carrier_config.auto_chain_to_fms:
        from . import dispatch as fms_dispatch
        try:
            fms_dispatch.dispatch_booking_confirmed(booking)
            logger.info(
                'Auto-chained FMS push for %s after carrier confirmation',
                booking.booking_number,
            )
        except Exception:
            logger.exception(
                'FMS push failed after carrier confirmation for %s',
                booking.booking_number,
            )


def _handle_rejected(booking, carrier_config, data):
    """Handle carrier rejection."""
    from bookings.models import Booking

    error_msg = data.get('message', 'Carrier rejected the booking request.')

    Booking.objects.filter(pk=booking.pk).update(
        carrier_request_status='REJECTED',
        carrier_request_error=error_msg[:1000],
    )
    booking.refresh_from_db()

    # Log rejection
    from .adapters.base import AdapterResult
    log_result = AdapterResult(
        success=False,
        response_data=data,
        error_message=error_msg,
    )
    _log_carrier_result(booking, carrier_config, 'CARRIER_REJECTED', log_result)

    logger.warning(
        'Carrier rejected booking %s: %s',
        booking.booking_number, error_msg,
    )


def _handle_amendment_required(booking, carrier_config, data):
    """Handle carrier amendment request (carrier needs changes before confirming)."""
    from bookings.models import Booking

    msg = data.get('message', 'Carrier requires amendments before confirming.')

    Booking.objects.filter(pk=booking.pk).update(
        carrier_request_status='REJECTED',
        carrier_request_error=f'Amendment required: {msg}'[:1000],
    )
    booking.refresh_from_db()

    from .adapters.base import AdapterResult
    log_result = AdapterResult(
        success=False,
        response_data=data,
        error_message=msg,
    )
    _log_carrier_result(booking, carrier_config, 'CARRIER_REJECTED', log_result)

    logger.warning(
        'Carrier requires amendments for %s: %s',
        booking.booking_number, msg,
    )
