"""
Claude API client for the LLM-powered import feature.

Encapsulates all Anthropic API communication. Sends file content + booking
schema + reference data to Claude and receives structured booking JSON.
"""
import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


class LLMExtractionError(Exception):
    """Raised when the LLM extraction fails."""
    pass


SYSTEM_PROMPT = """You are a freight logistics data extraction assistant. Your job is to parse
import files (CSV, Excel, PDF) and extract booking data that maps to a specific
freight booking system schema.

Rules:
1. Each booking MUST have at least one cargo item.
2. Map port names/codes to the closest match in the provided port reference list.
   Use the port CODE (e.g., "CNSHA"), not the name.
3. Map container descriptions to the closest match in the provided container type
   reference list. Use the container CODE (e.g., "20GP").
4. For transport_mode, map to one of: SEA_FCL, SEA_LCL, AIR, SEA_AIR, AIR_SEA, RAIL, TRUCK, MULTIMODAL.
   If the file mentions "ocean", "sea", "FCL", or "container", use SEA_FCL.
   If it mentions "LCL" or "less than container", use SEA_LCL.
   If it mentions "air" or "flight", use AIR.
   If it mentions "sea-air" or "sea then air", use SEA_AIR.
   If it mentions "air-sea" or "air then sea", use AIR_SEA.
5. For incoterms, map to one of: FOB, CFR, CIF, EXW, FCA, CPT, CIP, DAP, DPU, DDP, FAS.
   Default to FOB if not specified.
6. For package_type, map to one of: PALLET, CARTON, CRATE, DRUM, BAG, BUNDLE, PACKAGE, OTHER.
   Default to PACKAGE if unclear.
7. Dates must be in YYYY-MM-DD format. Convert any date format you encounter.
8. If a required field cannot be determined, set its value to null and add a
   message to the booking's "issues" array explaining what is missing.
9. Set "confidence" to "high", "medium", or "low" for each booking based on
   how well the data maps to the schema.
10. Be conservative: prefer null with an issue message over guessing incorrectly.
11. If multiple rows clearly belong to the same booking (same PO number, same
    route, etc.), group them as multiple cargo items under one booking.
12. Return ONLY valid JSON. No markdown fences, no explanation outside the JSON."""


def _build_user_message(file_content: str, reference_data: dict) -> str:
    """Build the user message with schema, reference data, and file content."""
    ports_json = json.dumps(reference_data['ports'], indent=None)
    container_types_json = json.dumps(reference_data['container_types'], indent=None)

    return f"""## Booking Schema

### Required Booking Fields:
- transport_mode (string): SEA_FCL | SEA_LCL | AIR | SEA_AIR | AIR_SEA | RAIL | TRUCK | MULTIMODAL
- origin_port_code (string): UN/LOCODE from the port reference list below
- destination_port_code (string): UN/LOCODE from the port reference list below
- cargo_ready_date (string): YYYY-MM-DD format
- container_type_code (string|null): Code from list below. REQUIRED for SEA_FCL. Optional/null for AIR, SEA_LCL, RAIL, TRUCK, MULTIMODAL.
- container_count (integer|null): >= 1. REQUIRED for SEA_FCL. null for other modes.

### Optional Booking Fields:
- incoterms (string): FOB | CFR | CIF | EXW | FCA | CPT | CIP | DAP | DPU | DDP | FAS (default: FOB)
- incoterms_location (string): named place for incoterms
- commodity_description (string): general commodity description
- is_hazardous (boolean): default false
- external_reference (string): customer PO/reference number
- special_instructions (string): any special handling notes
- chargeable_weight_kg (number|null): Chargeable weight for air freight (max of actual vs volumetric). null for non-air.
- flight_number (string|null): Flight number for air freight. null for non-air.

### Cargo Item Fields (at least 1 per booking):
Required: description (string), package_type (PALLET|CARTON|CRATE|DRUM|BAG|BUNDLE|PACKAGE|OTHER), quantity (integer >= 1), weight_kg (decimal > 0)
Optional: hs_code (6-10 digit string), volume_cbm (decimal), length_cm (decimal), width_cm (decimal), height_cm (decimal), marks_and_numbers (string), is_hazardous (boolean), un_number (4-digit string), imo_class (string), country_of_origin (2-char ISO code like CN, US, DE)

## Reference Data

### Valid Ports:
{ports_json}

### Valid Container Types:
{container_types_json}

## File Content to Parse:
{file_content}

## Required JSON Response Format:
{{
  "bookings": [
    {{
      "row_reference": "Row 2" or "Rows 2-4",
      "confidence": "high" or "medium" or "low",
      "issues": ["list of any problems or missing required data"],
      "booking": {{
        "transport_mode": "SEA_FCL",
        "origin_port_code": "CNSHA",
        "destination_port_code": "USLAX",
        "cargo_ready_date": "2026-03-15",
        "container_type_code": "20GP",
        "container_count": 1,
        "incoterms": "FOB",
        "incoterms_location": "",
        "commodity_description": "",
        "is_hazardous": false,
        "external_reference": "",
        "special_instructions": "",
        "chargeable_weight_kg": null,
        "flight_number": null
      }},
      "items": [
        {{
          "description": "Item description",
          "package_type": "CARTON",
          "quantity": 100,
          "weight_kg": 500.0,
          "hs_code": "",
          "volume_cbm": null,
          "length_cm": null,
          "width_cm": null,
          "height_cm": null,
          "marks_and_numbers": "",
          "is_hazardous": false,
          "un_number": "",
          "imo_class": "",
          "country_of_origin": ""
        }}
      ]
    }}
  ],
  "extraction_notes": "Summary of how the data was interpreted"
}}

Note: For AIR bookings, set container_type_code and container_count to null. For SEA_FCL, container fields are required."""


def _parse_response(response_text: str) -> dict:
    """Parse and validate the LLM response JSON."""
    # Strip markdown code fences if present
    text = response_text.strip()
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```', '', text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error('LLM response JSON parse error: %s\nResponse: %s', e, text[:500])
        raise LLMExtractionError(
            'AI returned an unparseable response. Please try again.'
        )

    if not isinstance(data, dict) or 'bookings' not in data:
        raise LLMExtractionError(
            'AI response missing expected "bookings" field.'
        )

    if not isinstance(data['bookings'], list):
        raise LLMExtractionError(
            'AI response "bookings" field is not a list.'
        )

    return data


def extract_bookings_from_content(file_content: str, reference_data: dict) -> dict:
    """
    Send file content + schema + reference data to Claude and receive
    structured booking data.

    Args:
        file_content: Text content extracted from the uploaded file.
        reference_data: Dict with 'ports' and 'container_types' lists.

    Returns:
        Dict with 'bookings' list and 'extraction_notes' string.

    Raises:
        LLMExtractionError: If API call fails or response is unparseable.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        raise LLMExtractionError(
            'Anthropic API key not configured. '
            'Please set the ANTHROPIC_API_KEY environment variable.'
        )

    model = getattr(settings, 'ANTHROPIC_MODEL', 'claude-sonnet-4-5-20250929')

    try:
        import anthropic
    except ImportError:
        raise LLMExtractionError(
            'The anthropic package is not installed. '
            'Run: pip install anthropic'
        )

    user_message = _build_user_message(file_content, reference_data)

    try:
        client = anthropic.Anthropic(api_key=api_key)

        logger.info(
            'Calling Claude API (model=%s) for file import extraction',
            model,
        )

        response = client.messages.create(
            model=model,
            max_tokens=16384,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[
                {'role': 'user', 'content': user_message},
            ],
        )

        response_text = response.content[0].text

        logger.debug(
            'Claude API response: %d chars, stop_reason=%s',
            len(response_text),
            response.stop_reason,
        )

        if response.stop_reason == 'max_tokens':
            logger.warning('Claude API response was truncated (max_tokens reached)')
            raise LLMExtractionError(
                'AI response was truncated — the file may contain too much data. '
                'Try splitting into smaller files.'
            )

        return _parse_response(response_text)

    except LLMExtractionError:
        raise
    except anthropic.RateLimitError:
        raise LLMExtractionError(
            'AI service rate limit reached. Please wait a moment and try again.'
        )
    except anthropic.APIStatusError as e:
        logger.error('Anthropic API error: %s', e)
        raise LLMExtractionError(
            f'AI service error: {e.message}'
        )
    except anthropic.APIConnectionError:
        raise LLMExtractionError(
            'Could not connect to AI service. Please check your internet connection.'
        )
    except Exception as e:
        logger.exception('Unexpected error calling Claude API')
        raise LLMExtractionError(f'AI extraction failed: {e}')
