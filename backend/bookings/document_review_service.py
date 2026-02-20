"""
AI-powered document review service.

Extracts structured data from uploaded shipping PDFs using pdfplumber
for text extraction and Claude for intelligent field parsing, then
validates the extracted data against the booking record.
"""
import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


class DocumentReviewError(Exception):
    """Raised when document review fails."""
    pass


# ── Severity levels ──────────────────────────────────────────────────

SEVERITY_HIGH = 'HIGH'
SEVERITY_MEDIUM = 'MEDIUM'
SEVERITY_LOW = 'LOW'

EXTRACTION_PROMPT = """You are a shipping document data extractor. Extract structured data from
the provided document text. This text was extracted from a PDF shipping document
(bill of lading, commercial invoice, packing list, cargo manifest, or similar).

Return ONLY valid JSON with the following schema. Use null for any field you cannot find.

{
  "document_type_detected": "BILL_OF_LADING" | "COMMERCIAL_INVOICE" | "PACKING_LIST" | "CARGO_MANIFEST" | "SHIPPING_ADVICE" | "OTHER",
  "shipper_name": "string or null",
  "consignee_name": "string or null",
  "notify_party_name": "string or null",
  "port_of_loading": "Port name or UN/LOCODE or null",
  "port_of_discharge": "Port name or UN/LOCODE or null",
  "vessel_name": "string or null",
  "voyage_number": "string or null",
  "bill_of_lading_number": "string or null",
  "booking_reference": "string or null",
  "containers": [
    {
      "container_number": "string",
      "seal_number": "string or null",
      "container_type": "string or null",
      "gross_weight_kg": number or null
    }
  ],
  "cargo_description": "string or null",
  "total_packages": number or null,
  "total_gross_weight_kg": number or null,
  "total_volume_cbm": number or null,
  "incoterms": "string or null",
  "commodity_hs_code": "string or null",
  "extraction_notes": "Brief notes about what was found or any ambiguities"
}

Rules:
1. Extract ALL fields you can find. Use null only if truly absent.
2. For ports, try to identify the UN/LOCODE (e.g., CNSHA, USLAX) if visible.
   Otherwise, return the port name exactly as shown.
3. For weights, convert to kilograms. If in tonnes, multiply by 1000.
4. Container numbers follow ISO 6346 format (4 letters + 7 digits, e.g., MSCU1234567).
5. Return ONLY the JSON object. No markdown fences, no explanation outside JSON."""


def extract_text_from_pdf(file_path):
    """Extract text and tables from a PDF using pdfplumber.

    Args:
        file_path: Path to the PDF file.

    Returns:
        str: Extracted text content.

    Raises:
        DocumentReviewError: If PDF cannot be read.
    """
    try:
        import pdfplumber
    except ImportError:
        raise DocumentReviewError(
            'pdfplumber is not installed. Run: pip install pdfplumber'
        )

    try:
        full_text = []
        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) > 20:
                raise DocumentReviewError(
                    'PDF has too many pages (max 20). '
                    'Please upload a shorter document.'
                )

            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text.append(f'--- Page {i + 1} ---')
                    full_text.append(page_text)

                # Extract tables separately for better structure
                tables = page.extract_tables()
                for table in tables:
                    if table:
                        full_text.append('\n[TABLE]')
                        for row in table:
                            cleaned = [str(cell or '').strip() for cell in row]
                            full_text.append(' | '.join(cleaned))
                        full_text.append('[/TABLE]\n')

        result = '\n'.join(full_text).strip()
        if not result:
            raise DocumentReviewError(
                'No text could be extracted from this PDF. '
                'It may be a scanned image — only digitally-generated PDFs are supported.'
            )

        # Truncate to avoid excessive token usage
        max_chars = 30000
        if len(result) > max_chars:
            result = result[:max_chars] + '\n\n[TRUNCATED — document too large]'

        return result

    except DocumentReviewError:
        raise
    except Exception as e:
        logger.exception('Error extracting PDF text: %s', e)
        raise DocumentReviewError(f'Failed to read PDF: {e}')


def extract_fields_with_llm(pdf_text):
    """Send extracted PDF text to Claude for structured field extraction.

    Args:
        pdf_text: Text extracted from the PDF.

    Returns:
        dict: Extracted fields as a dictionary.

    Raises:
        DocumentReviewError: If LLM call fails.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise DocumentReviewError(
            'Anthropic API key not configured. '
            'Please set the ANTHROPIC_API_KEY environment variable.'
        )

    model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5-20250929')

    try:
        import anthropic
    except ImportError:
        raise DocumentReviewError(
            'The anthropic package is not installed. '
            'Run: pip install anthropic'
        )

    try:
        client = anthropic.Anthropic(api_key=api_key)

        logger.info(
            'Calling Claude API (model=%s) for document review extraction',
            model,
        )

        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0,
            system=EXTRACTION_PROMPT,
            messages=[
                {'role': 'user', 'content': f'Extract data from this shipping document:\n\n{pdf_text}'},
            ],
        )

        response_text = response.content[0].text

        logger.debug(
            'Claude document review response: %d chars, stop_reason=%s',
            len(response_text),
            response.stop_reason,
        )

        # Parse JSON response
        text = response_text.strip()
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```', '', text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error('Document review JSON parse error: %s\nResponse: %s', e, text[:500])
            raise DocumentReviewError(
                'AI returned an unparseable response. Please try again.'
            )

        return data

    except DocumentReviewError:
        raise
    except anthropic.RateLimitError:
        raise DocumentReviewError(
            'AI service rate limit reached. Please wait a moment and try again.'
        )
    except anthropic.APIStatusError as e:
        logger.error('Anthropic API error during document review: %s', e)
        raise DocumentReviewError(f'AI service error: {e.message}')
    except anthropic.APIConnectionError:
        raise DocumentReviewError(
            'Could not connect to AI service. Please check your internet connection.'
        )
    except Exception as e:
        logger.exception('Unexpected error during document review LLM call')
        raise DocumentReviewError(f'AI extraction failed: {e}')


def _normalize_port_name(value):
    """Normalize a port name/code for fuzzy comparison."""
    if not value:
        return ''
    return re.sub(r'[^a-z0-9]', '', value.lower())


def _match_port(extracted_value, booking_port):
    """Check if an extracted port value matches a booking port.

    Compares against: port code, port name, and country.

    Returns:
        bool: True if the values match.
    """
    if not extracted_value or not booking_port:
        return True  # No data to compare — not a mismatch

    norm_extracted = _normalize_port_name(extracted_value)
    norm_code = _normalize_port_name(booking_port.code)
    norm_name = _normalize_port_name(booking_port.name)

    # Exact code match (e.g., CNSHA == CNSHA)
    if norm_extracted == norm_code:
        return True

    # Extracted value contains the port code
    if norm_code in norm_extracted:
        return True

    # Extracted value contains the port name
    if norm_name and norm_name in norm_extracted:
        return True

    # Port name contains the extracted value (e.g., "Shanghai" in "Port of Shanghai")
    if norm_extracted and norm_extracted in norm_name:
        return True

    return False


def _weight_close(extracted_weight, booking_weight, tolerance_kg=100):
    """Check if two weights are within tolerance."""
    if extracted_weight is None or booking_weight is None:
        return True  # No data to compare
    try:
        diff = abs(float(extracted_weight) - float(booking_weight))
        return diff <= tolerance_kg
    except (ValueError, TypeError):
        return True


def validate_against_booking(extracted_data, booking):
    """Compare extracted document fields against the booking record.

    Args:
        extracted_data: Dict of fields extracted by the LLM.
        booking: Booking model instance.

    Returns:
        list[dict]: List of discrepancy dicts, each with:
            - field: Human-readable field name
            - document_value: What the document says
            - booking_value: What the booking record says
            - severity: HIGH, MEDIUM, or LOW
            - message: Explanation of the discrepancy
    """
    discrepancies = []

    # ── Port of Loading (HIGH) ──
    pol = extracted_data.get('port_of_loading')
    if pol and not _match_port(pol, booking.origin_port):
        discrepancies.append({
            'field': 'Port of Loading',
            'document_value': pol,
            'booking_value': str(booking.origin_port),
            'severity': SEVERITY_HIGH,
            'message': 'The port of loading in the document does not match the booking origin port.',
        })

    # ── Port of Discharge (HIGH) ──
    pod = extracted_data.get('port_of_discharge')
    if pod and not _match_port(pod, booking.destination_port):
        discrepancies.append({
            'field': 'Port of Discharge',
            'document_value': pod,
            'booking_value': str(booking.destination_port),
            'severity': SEVERITY_HIGH,
            'message': 'The port of discharge in the document does not match the booking destination port.',
        })

    # ── Shipper Name (MEDIUM) ──
    shipper = extracted_data.get('shipper_name')
    if shipper:
        # Check against booking parties with SHIPPER role
        shipper_parties = booking.booking_parties.filter(role='SHIPPER')
        customer_name = booking.customer.name
        norm_shipper = _normalize_port_name(shipper)

        matched = False
        if norm_shipper in _normalize_port_name(customer_name):
            matched = True
        elif _normalize_port_name(customer_name) in norm_shipper:
            matched = True
        if not matched:
            for bp in shipper_parties:
                if _normalize_port_name(bp.company_name) in norm_shipper:
                    matched = True
                    break
                if norm_shipper in _normalize_port_name(bp.company_name):
                    matched = True
                    break

        if not matched:
            booking_shipper = (
                shipper_parties.first().company_name if shipper_parties.exists()
                else customer_name
            )
            discrepancies.append({
                'field': 'Shipper',
                'document_value': shipper,
                'booking_value': booking_shipper,
                'severity': SEVERITY_MEDIUM,
                'message': 'The shipper name in the document does not match the booking customer or shipper party.',
            })

    # ── Consignee Name (MEDIUM) ──
    consignee = extracted_data.get('consignee_name')
    if consignee:
        consignee_parties = booking.booking_parties.filter(role='CONSIGNEE')
        if consignee_parties.exists():
            norm_consignee = _normalize_port_name(consignee)
            matched = any(
                _normalize_port_name(bp.company_name) in norm_consignee
                or norm_consignee in _normalize_port_name(bp.company_name)
                for bp in consignee_parties
            )
            if not matched:
                discrepancies.append({
                    'field': 'Consignee',
                    'document_value': consignee,
                    'booking_value': consignee_parties.first().company_name,
                    'severity': SEVERITY_MEDIUM,
                    'message': 'The consignee in the document does not match the booking consignee party.',
                })

    # ── Total Weight (MEDIUM) ──
    doc_weight = extracted_data.get('total_gross_weight_kg')
    if doc_weight is not None and booking.total_weight_kg:
        if not _weight_close(doc_weight, booking.total_weight_kg):
            discrepancies.append({
                'field': 'Total Gross Weight',
                'document_value': f'{doc_weight} kg',
                'booking_value': f'{booking.total_weight_kg} kg',
                'severity': SEVERITY_MEDIUM,
                'message': f'Weight difference exceeds 100 kg tolerance.',
            })

    # ── Total Volume (MEDIUM) ──
    doc_volume = extracted_data.get('total_volume_cbm')
    if doc_volume is not None and booking.total_volume_cbm:
        try:
            vol_diff = abs(float(doc_volume) - float(booking.total_volume_cbm))
            if vol_diff > 1.0:  # 1 CBM tolerance
                discrepancies.append({
                    'field': 'Total Volume',
                    'document_value': f'{doc_volume} CBM',
                    'booking_value': f'{booking.total_volume_cbm} CBM',
                    'severity': SEVERITY_MEDIUM,
                    'message': 'Volume difference exceeds 1 CBM tolerance.',
                })
        except (ValueError, TypeError):
            pass

    # ── Container Numbers (MEDIUM) ──
    doc_containers = extracted_data.get('containers') or []
    if doc_containers:
        booking_items = list(booking.items.values_list('marks_and_numbers', flat=True))
        # Also check external_reference and carrier_booking_ref
        all_refs = ' '.join(filter(None, booking_items))
        for container in doc_containers:
            container_num = container.get('container_number', '')
            if container_num and container_num not in all_refs:
                # Container not found in booking — only flag if booking has items
                if booking.items.exists():
                    discrepancies.append({
                        'field': 'Container Number',
                        'document_value': container_num,
                        'booking_value': 'Not found in booking items',
                        'severity': SEVERITY_MEDIUM,
                        'message': f'Container {container_num} from document not found in booking cargo items.',
                    })

    # ── Booking Reference (MEDIUM) ──
    doc_ref = extracted_data.get('booking_reference')
    if doc_ref:
        norm_ref = _normalize_port_name(doc_ref)
        booking_refs = [
            _normalize_port_name(booking.booking_number),
            _normalize_port_name(booking.external_reference),
            _normalize_port_name(booking.carrier_booking_ref),
        ]
        if norm_ref not in booking_refs:
            discrepancies.append({
                'field': 'Booking Reference',
                'document_value': doc_ref,
                'booking_value': booking.booking_number,
                'severity': SEVERITY_MEDIUM,
                'message': 'The booking reference in the document does not match the booking number or external reference.',
            })

    # ── Cargo Description (LOW) ──
    doc_desc = extracted_data.get('cargo_description')
    if doc_desc and booking.commodity_description:
        # Use lowercase with spaces preserved for word splitting
        norm_doc = re.sub(r'[^a-z0-9\s]', '', doc_desc.lower()).strip()
        norm_booking = re.sub(r'[^a-z0-9\s]', '', booking.commodity_description.lower()).strip()
        # Only flag if there's absolutely no overlap
        words_doc = set(norm_doc.split()) if norm_doc else set()
        words_booking = set(norm_booking.split()) if norm_booking else set()
        if words_doc and words_booking and not words_doc.intersection(words_booking):
            discrepancies.append({
                'field': 'Cargo Description',
                'document_value': doc_desc[:100],
                'booking_value': booking.commodity_description[:100],
                'severity': SEVERITY_LOW,
                'message': 'Cargo descriptions do not appear to match.',
            })

    # ── INCOTERMS (LOW) ──
    doc_incoterms = extracted_data.get('incoterms')
    if doc_incoterms and booking.incoterms:
        if doc_incoterms.upper().strip() != booking.incoterms.upper().strip():
            discrepancies.append({
                'field': 'INCOTERMS',
                'document_value': doc_incoterms,
                'booking_value': booking.incoterms,
                'severity': SEVERITY_LOW,
                'message': 'INCOTERMS in the document differ from the booking.',
            })

    return discrepancies


def review_document(document, booking):
    """Full document review pipeline: extract text, parse with LLM, validate.

    Args:
        document: BookingDocument instance (must be a PDF).
        booking: Booking instance the document belongs to.

    Returns:
        dict: {
            'extracted_data': dict of extracted fields,
            'discrepancies': list of discrepancy dicts,
            'summary': str summary message,
        }

    Raises:
        DocumentReviewError: If the review cannot be completed.
    """
    if document.file_extension != '.pdf':
        raise DocumentReviewError(
            'AI Document Review only supports PDF files. '
            f'This file is {document.file_extension}.'
        )

    # Step 1: Extract text from PDF
    pdf_text = extract_text_from_pdf(document.file.path)

    # Step 2: Extract structured fields with LLM
    extracted_data = extract_fields_with_llm(pdf_text)

    # Step 3: Validate against booking
    discrepancies = validate_against_booking(extracted_data, booking)

    # Build summary
    high = sum(1 for d in discrepancies if d['severity'] == SEVERITY_HIGH)
    medium = sum(1 for d in discrepancies if d['severity'] == SEVERITY_MEDIUM)
    low = sum(1 for d in discrepancies if d['severity'] == SEVERITY_LOW)

    if not discrepancies:
        summary = 'All extracted fields match the booking record. No discrepancies found.'
    else:
        parts = []
        if high:
            parts.append(f'{high} critical')
        if medium:
            parts.append(f'{medium} important')
        if low:
            parts.append(f'{low} minor')
        summary = f'Found {len(discrepancies)} discrepancies: {", ".join(parts)}.'

    return {
        'extracted_data': extracted_data,
        'discrepancies': discrepancies,
        'summary': summary,
    }
