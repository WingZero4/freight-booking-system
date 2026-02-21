"""Create bookings from uploaded PDF documents using AI extraction."""

import logging

logger = logging.getLogger(__name__)


def extract_booking_data_from_pdf(file_path):
    """Extract booking-relevant fields from a PDF document.

    Uses the existing document_review_service for extraction,
    then maps fields to booking form initial data.
    """
    from .document_review_service import extract_text_from_pdf, extract_fields_with_llm

    pdf_text = extract_text_from_pdf(file_path)
    if not pdf_text:
        return None, 'Could not extract text from PDF.'

    extracted = extract_fields_with_llm(pdf_text)
    if not extracted:
        return None, 'AI extraction returned no data.'

    return extracted, None


def map_extracted_to_form_data(extracted_data):
    """Map AI-extracted data to BookingForm initial values.

    Returns dict suitable for BookingForm(initial=...).
    """
    from .models import Port, Party

    form_data = {}

    # Port resolution
    pol = extracted_data.get('port_of_loading', '')
    pod = extracted_data.get('port_of_discharge', '')
    if pol:
        form_data['origin_port'] = _resolve_port(pol)
    if pod:
        form_data['destination_port'] = _resolve_port(pod)

    # Cargo description
    cargo_desc = extracted_data.get('cargo_description', '')
    if cargo_desc:
        form_data['commodity_description'] = cargo_desc

    # Incoterms
    incoterms = extracted_data.get('incoterms', '')
    if incoterms:
        form_data['incoterms'] = incoterms.upper()

    # External reference
    booking_ref = extracted_data.get('booking_reference', '')
    if booking_ref:
        form_data['external_reference'] = booking_ref

    # Weight/volume
    total_weight = extracted_data.get('total_weight_kg')
    if total_weight:
        try:
            form_data['total_weight_kg'] = float(total_weight)
        except (ValueError, TypeError):
            pass

    total_volume = extracted_data.get('total_volume_cbm')
    if total_volume:
        try:
            form_data['total_volume_cbm'] = float(total_volume)
        except (ValueError, TypeError):
            pass

    # Vessel info
    vessel = extracted_data.get('vessel_name', '')
    voyage = extracted_data.get('voyage_number', '')
    if vessel:
        form_data['vessel_name'] = vessel
    if voyage:
        form_data['voyage_number'] = voyage

    # Items from containers
    items_data = []
    containers = extracted_data.get('containers', [])
    if containers:
        for c in containers:
            item = {}
            if c.get('description'):
                item['description'] = c['description']
            if c.get('weight_kg'):
                try:
                    item['weight_kg'] = float(c['weight_kg'])
                except (ValueError, TypeError):
                    pass
            if item:
                items_data.append(item)

    # Parties
    parties = {}
    shipper = extracted_data.get('shipper', {})
    if shipper and shipper.get('name'):
        parties['SHIPPER'] = shipper
    consignee = extracted_data.get('consignee', {})
    if consignee and consignee.get('name'):
        parties['CONSIGNEE'] = consignee
    notify = extracted_data.get('notify_party', {})
    if notify and notify.get('name'):
        parties['NOTIFY'] = notify

    return {
        'form_data': form_data,
        'items_data': items_data,
        'parties': parties,
        'extraction_notes': extracted_data.get('extraction_notes', ''),
    }


def _resolve_port(port_text):
    """Try to match port text to a Port model instance.

    Tries: exact code match, name substring, case-insensitive.
    Returns Port.id or None.
    """
    from .models import Port

    port_text = port_text.strip().upper()

    # Exact code match
    port = Port.objects.filter(code__iexact=port_text).first()
    if port:
        return port.id

    # Name contains match
    port = Port.objects.filter(name__icontains=port_text).first()
    if port:
        return port.id

    # Code contains match
    port = Port.objects.filter(code__icontains=port_text).first()
    if port:
        return port.id

    return None
