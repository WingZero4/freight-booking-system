"""
EDIFACT IFTMBF (Firm Booking) inbound parser.

Parses standard IFTMBF message segments into a booking data dict
compatible with BookingService.create_booking_from_data().

IFTMBF segment structure (simplified):
  UNH - Message header
  BGM - Beginning of message (booking reference)
  DTM - Date/time (cargo ready date, ETD, etc.)
  TSR - Transport service requirements
  FTX - Free text (special instructions)
  LOC - Location (origin/destination ports)
  NAD - Name and address (shipper, consignee, etc.)
  GID - Goods item detail
  MEA - Measurements
  DGS - Dangerous goods
  UNT - Message trailer
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class IFTMBFParseError(Exception):
    """Error parsing IFTMBF message."""
    pass


def parse_iftmbf(message_text):
    """
    Parse an EDIFACT IFTMBF message into a booking data dict.

    Args:
        message_text: Raw EDIFACT message as string.

    Returns:
        dict with keys:
            booking_data: dict for BookingService.create_booking_from_data()
            items_data: list of item dicts
            parties_data: list of party dicts
            external_reference: customer reference from BGM
            issues: list of warning strings

    Raises:
        IFTMBFParseError on fatal parse errors.
    """
    segments = _split_segments(message_text)

    if not segments:
        raise IFTMBFParseError('No segments found in message.')

    result = {
        'booking_data': {},
        'items_data': [],
        'parties_data': [],
        'external_reference': '',
        'issues': [],
    }

    current_item = None

    for segment in segments:
        tag = segment[:3]

        if tag == 'BGM':
            _parse_bgm(segment, result)
        elif tag == 'DTM':
            _parse_dtm(segment, result)
        elif tag == 'TSR':
            _parse_tsr(segment, result)
        elif tag == 'FTX':
            _parse_ftx(segment, result, current_item)
        elif tag == 'LOC':
            _parse_loc(segment, result)
        elif tag == 'NAD':
            _parse_nad(segment, result)
        elif tag == 'GID':
            current_item = {}
            result['items_data'].append(current_item)
            _parse_gid(segment, current_item)
        elif tag == 'MEA':
            _parse_mea(segment, current_item)
        elif tag == 'DGS':
            _parse_dgs(segment, current_item)

    # Defaults
    if 'transport_mode' not in result['booking_data']:
        result['booking_data']['transport_mode'] = 'SEA_FCL'
    if 'incoterms' not in result['booking_data']:
        result['booking_data']['incoterms'] = 'FOB'

    if not result['items_data']:
        result['issues'].append('No goods items (GID) found in message.')

    return result


def _split_segments(message_text):
    """Split EDIFACT message into segments."""
    text = message_text.replace('\r', '').replace('\n', '')
    segments = [s.strip() for s in text.split("'") if s.strip()]
    return segments


def _parse_elements(segment):
    """Split segment into data elements by + delimiter, sub-elements by :."""
    elements = segment.split('+')
    return [e.split(':') for e in elements]


def _parse_bgm(segment, result):
    """Parse BGM (Beginning of Message) — extract booking reference."""
    elements = _parse_elements(segment)
    if len(elements) > 2:
        ref = elements[2][0] if elements[2] else ''
        result['external_reference'] = ref
        result['booking_data']['external_reference'] = ref


def _parse_dtm(segment, result):
    """Parse DTM (Date/Time) — extract dates."""
    elements = _parse_elements(segment)
    if len(elements) > 1 and len(elements[1]) >= 2:
        qualifier = elements[1][0]
        date_str = elements[1][1]
        date_format = elements[1][2] if len(elements[1]) > 2 else '102'

        parsed_date = _parse_edifact_date(date_str, date_format)
        if not parsed_date:
            return

        if qualifier == '133':  # Cargo ready date
            result['booking_data']['cargo_ready_date'] = parsed_date
        elif qualifier == '132':  # Estimated departure
            result['booking_data']['etd'] = parsed_date
        elif qualifier == '178':  # Estimated arrival
            result['booking_data']['eta'] = parsed_date


def _parse_edifact_date(date_str, format_code='102'):
    """Parse EDIFACT date string to Python date."""
    try:
        if format_code == '102':  # CCYYMMDD
            return datetime.strptime(date_str, '%Y%m%d').date()
        elif format_code == '203':  # CCYYMMDDHHMM
            return datetime.strptime(date_str[:8], '%Y%m%d').date()
        elif format_code == '101':  # YYMMDD
            return datetime.strptime(date_str, '%y%m%d').date()
    except (ValueError, TypeError):
        return None
    return None


def _parse_tsr(segment, result):
    """Parse TSR (Transport Service Requirements)."""
    raw = segment.upper()
    if 'FCL' in raw:
        result['booking_data']['transport_mode'] = 'SEA_FCL'
    elif 'LCL' in raw:
        result['booking_data']['transport_mode'] = 'SEA_LCL'


def _parse_ftx(segment, result, current_item):
    """Parse FTX (Free Text)."""
    elements = _parse_elements(segment)
    if len(elements) > 4:
        text = ':'.join(elements[4])
    elif len(elements) > 3:
        text = ':'.join(elements[3])
    else:
        return

    if current_item is not None:
        if 'description' in current_item:
            current_item['description'] += f' {text}'
        else:
            current_item['description'] = text
    else:
        qualifier = elements[1][0] if len(elements) > 1 and elements[1] else ''
        if qualifier == 'AAA':
            result['booking_data']['special_instructions'] = text
        elif qualifier == 'AAI':
            result['booking_data']['commodity_description'] = text


def _parse_loc(segment, result):
    """Parse LOC (Location) — origin/destination ports."""
    elements = _parse_elements(segment)
    if len(elements) > 2:
        qualifier = elements[1][0] if elements[1] else ''
        port_code = elements[2][0] if elements[2] else ''

        if qualifier == '88':  # Place of loading (origin)
            result['booking_data']['origin_port_code'] = port_code
        elif qualifier == '11':  # Place of discharge (destination)
            result['booking_data']['destination_port_code'] = port_code


def _parse_nad(segment, result):
    """Parse NAD (Name and Address) — parties."""
    elements = _parse_elements(segment)
    if len(elements) < 4:
        return

    qualifier = elements[1][0] if elements[1] else ''
    role_map = {
        'CZ': 'SHIPPER',
        'CN': 'CONSIGNEE',
        'NI': 'NOTIFY',
        'FW': 'FREIGHT_FORWARDER',
    }
    role = role_map.get(qualifier)
    if not role:
        return

    party = {'role': role}
    if len(elements) > 4:
        party['company_name'] = ':'.join(elements[4])[:255]
    else:
        party['company_name'] = 'Unknown'

    address_parts = []
    for i in range(5, min(len(elements), 9)):
        addr = ':'.join(elements[i])
        if addr:
            address_parts.append(addr)
    party['address_text'] = ', '.join(address_parts)

    result['parties_data'].append(party)


def _parse_gid(segment, item):
    """Parse GID (Goods Item Detail)."""
    elements = _parse_elements(segment)
    if len(elements) > 2:
        sub = elements[2]
        item['quantity'] = int(sub[0]) if sub[0].isdigit() else 1
        pkg_map = {
            'CT': 'CARTON', 'PK': 'PACKAGE', 'PL': 'PALLET',
            'DR': 'DRUM', 'BG': 'BAG', 'CR': 'CRATE', 'BN': 'BUNDLE',
        }
        if len(sub) > 1:
            item['package_type'] = pkg_map.get(sub[1], 'PACKAGE')
        else:
            item['package_type'] = 'PACKAGE'

    if len(elements) > 3:
        item['description'] = ':'.join(elements[3])[:500]

    item.setdefault('quantity', 1)
    item.setdefault('weight_kg', 0)
    item.setdefault('description', 'EDI goods item')


def _parse_mea(segment, item):
    """Parse MEA (Measurements)."""
    if item is None:
        return
    elements = _parse_elements(segment)
    if len(elements) > 3:
        qualifier = elements[1][0] if elements[1] else ''
        # C174 composite: unit_qualifier:value — value at index 1
        sub = elements[3]
        if len(sub) > 1:
            value_str = sub[1]
        else:
            value_str = sub[0] if sub else ''

        try:
            value = float(value_str)
        except (ValueError, TypeError):
            return

        if qualifier in ('WT', 'AAA'):
            item['weight_kg'] = value
        elif qualifier == 'VOL':
            item['volume_cbm'] = value
        elif qualifier == 'LN':
            item['length_cm'] = value
        elif qualifier == 'WD':
            item['width_cm'] = value
        elif qualifier == 'HT':
            item['height_cm'] = value


def _parse_dgs(segment, item):
    """Parse DGS (Dangerous Goods)."""
    if item is None:
        return
    elements = _parse_elements(segment)
    item['is_hazardous'] = True
    if len(elements) > 2:
        item['un_number'] = (elements[2][0] if elements[2] else '')[:4]
    if len(elements) > 3:
        item['imo_class'] = (elements[3][0] if elements[3] else '')[:10]
