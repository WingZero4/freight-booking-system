"""
EDIFACT IFTMBC (Booking Confirmation) outbound generator.

Generates a basic IFTMBC message from a confirmed booking.
"""
from django.utils import timezone


def generate_iftmbc(booking):
    """
    Generate an EDIFACT IFTMBC message for a confirmed booking.

    Args:
        booking: Booking instance (should be CONFIRMED or later).

    Returns:
        str: EDIFACT message text.
    """
    segments = []
    now = timezone.now()

    # UNH - Message Header
    segments.append(f"UNH+1+IFTMBC:D:99B:UN'")

    # BGM - Beginning of Message (booking confirmation)
    segments.append(f"BGM+335+{booking.booking_number}+9'")

    # DTM - Message date
    segments.append(f"DTM+137:{now.strftime('%Y%m%d')}:102'")

    # DTM - Cargo ready date
    if booking.cargo_ready_date:
        segments.append(
            f"DTM+133:{booking.cargo_ready_date.strftime('%Y%m%d')}:102'"
        )

    # DTM - ETD
    if booking.etd:
        segments.append(f"DTM+132:{booking.etd.strftime('%Y%m%d')}:102'")

    # DTM - ETA
    if booking.eta:
        segments.append(f"DTM+178:{booking.eta.strftime('%Y%m%d')}:102'")

    # LOC - Origin
    if booking.origin_port:
        segments.append(f"LOC+88+{booking.origin_port.code}'")

    # LOC - Destination
    if booking.destination_port:
        segments.append(f"LOC+11+{booking.destination_port.code}'")

    # RFF - Reference numbers
    if booking.carrier_booking_ref:
        segments.append(f"RFF+BN:{booking.carrier_booking_ref}'")
    if booking.hbl_number:
        segments.append(f"RFF+BM:{booking.hbl_number}'")
    if booking.mbl_number:
        segments.append(f"RFF+MB:{booking.mbl_number}'")

    # NAD - Parties
    role_map = {
        'SHIPPER': 'CZ',
        'CONSIGNEE': 'CN',
        'NOTIFY': 'NI',
        'FREIGHT_FORWARDER': 'FW',
    }
    for bp in booking.booking_parties.all():
        edi_role = role_map.get(bp.role)
        if edi_role:
            segments.append(
                f"NAD+{edi_role}+++{bp.company_name}+{bp.address_text}'"
            )

    # GID + MEA for each item
    pkg_map = {
        'CARTON': 'CT', 'PACKAGE': 'PK', 'PALLET': 'PL',
        'DRUM': 'DR', 'BAG': 'BG', 'CRATE': 'CR', 'BUNDLE': 'BN',
    }
    for i, item in enumerate(booking.items.all(), 1):
        pkg_code = pkg_map.get(item.package_type, 'PK')
        segments.append(
            f"GID+{i}+{item.quantity}:{pkg_code}+{item.description}'"
        )
        segments.append(
            f"MEA+WT+AAA+KGM:{item.weight_kg}'"
        )
        if item.volume_cbm:
            segments.append(
                f"MEA+VOL+AAW+MTQ:{item.volume_cbm}'"
            )
        if item.is_hazardous:
            segments.append(
                f"DGS+IMD+{item.un_number}+{item.imo_class}'"
            )

    # UNT - Message Trailer
    segment_count = len(segments) + 1
    segments.append(f"UNT+{segment_count}+1'")

    return '\n'.join(segments)
