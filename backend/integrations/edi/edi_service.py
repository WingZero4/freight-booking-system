"""
EDI import service — processes IFTMBF files into bookings.

Bridges the IFTMBF parser with BookingService.
"""
import logging

from bookings.models import Port
from bookings.services import BookingService

from .iftmbf_parser import parse_iftmbf, IFTMBFParseError

logger = logging.getLogger(__name__)


class EDIImportError(Exception):
    pass


def process_edi_file(file_content, customer, user, request=None):
    """
    Parse an IFTMBF EDI file and create bookings.

    Args:
        file_content: Raw EDI message text (str).
        customer: Customer instance.
        user: User performing the import.
        request: Optional HttpRequest.

    Returns:
        dict with:
            created: list of booking numbers created
            errors: list of error message strings
            warnings: list of warning strings
    """
    result = {'created': [], 'errors': [], 'warnings': []}

    try:
        parsed = parse_iftmbf(file_content)
    except IFTMBFParseError as e:
        result['errors'].append(f'EDI parse error: {e}')
        return result

    result['warnings'] = parsed.get('issues', [])

    booking_data = parsed['booking_data']
    items_data = parsed['items_data']
    parties_data = parsed.get('parties_data', [])

    if not items_data:
        result['errors'].append('No cargo items found in EDI message.')
        return result

    # Resolve port codes to Port instances
    origin_code = booking_data.pop('origin_port_code', None)
    dest_code = booking_data.pop('destination_port_code', None)

    if origin_code:
        try:
            booking_data['origin_port'] = Port.objects.get(
                code=origin_code, is_active=True,
            )
        except Port.DoesNotExist:
            result['errors'].append(f'Unknown origin port: {origin_code}')
            return result
    else:
        result['errors'].append('Origin port not found in EDI message.')
        return result

    if dest_code:
        try:
            booking_data['destination_port'] = Port.objects.get(
                code=dest_code, is_active=True,
            )
        except Port.DoesNotExist:
            result['errors'].append(f'Unknown destination port: {dest_code}')
            return result
    else:
        result['errors'].append('Destination port not found in EDI message.')
        return result

    # Ensure required fields have defaults
    if 'cargo_ready_date' not in booking_data:
        from datetime import date, timedelta
        booking_data['cargo_ready_date'] = date.today() + timedelta(days=7)
        result['warnings'].append(
            'No cargo ready date in EDI, defaulted to 7 days from now.',
        )

    # Validate items have minimum required fields
    for i, item in enumerate(items_data):
        if not item.get('weight_kg') or float(item.get('weight_kg', 0)) <= 0:
            item['weight_kg'] = 1.0
            result['warnings'].append(
                f'Item {i + 1}: weight defaulted to 1.0 kg.',
            )
        if not item.get('description'):
            item['description'] = 'EDI cargo item'
            result['warnings'].append(
                f'Item {i + 1}: description defaulted.',
            )

    # Run cross-field validation (same checks as API serializer).
    # Container fields missing from EDI are treated as warnings (not errors)
    # since the booking is created as DRAFT for operators to complete.
    from bookings.validators import validate_booking_data
    validation_errors = validate_booking_data(booking_data)
    container_fields = {'container_type', 'container_count'}
    hard_errors = {k: v for k, v in validation_errors.items() if k not in container_fields}
    soft_errors = {k: v for k, v in validation_errors.items() if k in container_fields}
    if hard_errors:
        for field, msg in hard_errors.items():
            result['errors'].append(f'{field}: {msg}')
        return result
    for field, msg in soft_errors.items():
        result['warnings'].append(f'{field}: {msg} (requires operator completion)')

    try:
        booking = BookingService.create_booking_from_data(
            data=booking_data,
            items_data=items_data,
            customer=customer,
            user=user,
            request=request,
            source_channel='EDI',
            parties_data=parties_data or None,
        )
        result['created'].append(booking.booking_number)
    except Exception as e:
        logger.exception('Failed to create booking from EDI')
        result['errors'].append(f'Booking creation failed: {e}')

    return result
