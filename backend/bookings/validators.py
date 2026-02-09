"""
Pure validation functions for the freight booking system.

These validators contain NO database access — they operate only on the values
passed in. This makes them reusable across all input channels (web forms, API,
EDI, CSV import) and easy to unit-test.

Database-dependent validation (uniqueness, foreign key existence, permissions)
belongs in services.py.
"""
import re
from datetime import date
from decimal import Decimal, InvalidOperation


# ─── Constants ────────────────────────────────────────────────────────

INCOTERMS_CODES = frozenset([
    'FOB', 'CFR', 'CIF', 'EXW', 'FCA', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP', 'FAS',
])

PACKAGE_TYPES = frozenset([
    'PALLET', 'CARTON', 'CRATE', 'DRUM', 'BAG', 'BUNDLE', 'PACKAGE', 'OTHER',
])

DOCUMENT_TYPES = frozenset([
    'COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING',
    'AIRWAY_BILL', 'CUSTOMS_DECLARATION', 'CERTIFICATE_OF_ORIGIN',
    'SHIPPING_ADVICE', 'CARGO_MANIFEST', 'LOADING_PLAN',
    'INSURANCE_CERTIFICATE', 'FUMIGATION_CERT', 'INSPECTION_REPORT',
    'OTHER',
])

PARTY_ROLES = frozenset([
    'SHIPPER', 'CONSIGNEE', 'NOTIFY', 'BROKER', 'FREIGHT_FORWARDER', 'OTHER',
])

ALLOWED_FILE_EXTENSIONS = frozenset(['pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv'])
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# HS code: 6-10 digit numeric string
HS_CODE_PATTERN = re.compile(r'^\d{6,10}$')

# UN number: 4-digit string
UN_NUMBER_PATTERN = re.compile(r'^\d{4}$')

# ISO 3166-1 alpha-2 country code pattern
COUNTRY_CODE_PATTERN = re.compile(r'^[A-Z]{2}$')


# ─── Booking-level validators ────────────────────────────────────────

def validate_ports_different(origin_port_id, destination_port_id):
    """Origin and destination ports must differ."""
    if origin_port_id and destination_port_id and origin_port_id == destination_port_id:
        return 'Origin and destination ports must be different.'
    return None


def validate_cargo_ready_date(cargo_date, existing_date=None):
    """Cargo ready date must not be in the past (unless unchanged on edit)."""
    if not isinstance(cargo_date, date):
        return 'Invalid date format.'
    if existing_date and cargo_date == existing_date:
        return None  # Allow unchanged date on edit
    if cargo_date < date.today():
        return 'Cargo ready date cannot be in the past.'
    return None


def validate_container_count(count):
    """Container count must be between 1 and 999."""
    try:
        count = int(count)
    except (TypeError, ValueError):
        return 'Container count must be a number.'
    if count < 1 or count > 999:
        return 'Container count must be between 1 and 999.'
    return None


def validate_incoterms(code):
    """INCOTERMS must be a valid 2020 code."""
    if not code:
        return 'INCOTERMS is required.'
    if code.upper() not in INCOTERMS_CODES:
        return f'Invalid INCOTERMS code: {code}. Must be one of: {", ".join(sorted(INCOTERMS_CODES))}'
    return None


# ─── Cargo item validators ───────────────────────────────────────────

def validate_quantity(qty):
    """Quantity must be a positive integer, max 99,999."""
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        return 'Quantity must be a whole number.'
    if qty < 1:
        return 'Quantity must be at least 1.'
    if qty > 99999:
        return 'Quantity cannot exceed 99,999.'
    return None


def validate_weight_kg(weight):
    """Weight must be positive, max 99,999,999 kg."""
    try:
        weight = Decimal(str(weight))
    except (InvalidOperation, TypeError, ValueError):
        return 'Weight must be a number.'
    if weight <= 0:
        return 'Weight must be greater than 0.'
    if weight > 99999999:
        return 'Weight exceeds maximum allowed value.'
    return None


def validate_volume_cbm(volume):
    """Volume must be positive if provided."""
    if volume is None or volume == '':
        return None
    try:
        volume = Decimal(str(volume))
    except (InvalidOperation, TypeError, ValueError):
        return 'Volume must be a number.'
    if volume <= 0:
        return 'Volume must be greater than 0.'
    if volume > 9999999:
        return 'Volume exceeds maximum allowed value.'
    return None


def validate_dimensions(length, width, height):
    """If any dimension is provided, all must be provided and positive."""
    dims = [length, width, height]
    provided = [d for d in dims if d is not None and d != '']

    if not provided:
        return None  # All empty is fine

    if len(provided) != 3:
        return 'If providing dimensions, all three (length, width, height) are required.'

    for label, val in zip(['Length', 'Width', 'Height'], dims):
        try:
            val = Decimal(str(val))
        except (InvalidOperation, TypeError, ValueError):
            return f'{label} must be a number.'
        if val <= 0:
            return f'{label} must be greater than 0.'
        if val > 999999:
            return f'{label} exceeds maximum allowed value.'

    return None


def validate_hs_code(code):
    """HS code must be 6-10 digits if provided."""
    if not code:
        return None
    code = str(code).strip()
    if not HS_CODE_PATTERN.match(code):
        return 'HS code must be 6 to 10 digits.'
    return None


def validate_hazardous_fields(is_hazardous, un_number='', imo_class=''):
    """If marked hazardous, UN number and IMO class are required."""
    if not is_hazardous:
        return None
    errors = []
    if not un_number:
        errors.append('UN number is required for hazardous goods.')
    elif not UN_NUMBER_PATTERN.match(str(un_number).strip()):
        errors.append('UN number must be exactly 4 digits.')
    if not imo_class:
        errors.append('IMO class is required for hazardous goods.')
    return '; '.join(errors) if errors else None


def validate_country_code(code):
    """Country code must be ISO 3166-1 alpha-2 if provided."""
    if not code:
        return None
    code = str(code).strip().upper()
    if not COUNTRY_CODE_PATTERN.match(code):
        return 'Country code must be a 2-letter ISO code (e.g. US, CN, DE).'
    return None


def validate_package_type(ptype):
    """Package type must be a recognized value."""
    if not ptype:
        return 'Package type is required.'
    if ptype.upper() not in PACKAGE_TYPES:
        return f'Invalid package type: {ptype}. Must be one of: {", ".join(sorted(PACKAGE_TYPES))}'
    return None


# ─── Party validators ────────────────────────────────────────────────

def validate_party_role(role):
    """Party role must be a recognized value."""
    if not role:
        return 'Party role is required.'
    if role.upper() not in PARTY_ROLES:
        return f'Invalid party role: {role}. Must be one of: {", ".join(sorted(PARTY_ROLES))}'
    return None


def validate_party_company_name(name):
    """Company name is required and must not exceed 255 characters."""
    if not name or not name.strip():
        return 'Company name is required.'
    if len(name.strip()) > 255:
        return 'Company name must not exceed 255 characters.'
    return None


# ─── Document validators ─────────────────────────────────────────────

def validate_file_extension(filename):
    """File must have an allowed extension."""
    if not filename:
        return 'No file provided.'
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if ext not in ALLOWED_FILE_EXTENSIONS:
        return f'File type .{ext} is not allowed. Allowed: {", ".join(sorted(ALLOWED_FILE_EXTENSIONS))}'
    return None


def validate_file_size(size_bytes):
    """File must not exceed the maximum size."""
    if size_bytes > MAX_FILE_SIZE_BYTES:
        size_mb = size_bytes / (1024 * 1024)
        return f'File size ({size_mb:.1f} MB) exceeds maximum allowed size (10 MB).'
    return None


def validate_document_type(doc_type):
    """Document type must be a recognized value."""
    if not doc_type:
        return 'Document type is required.'
    if doc_type.upper() not in DOCUMENT_TYPES:
        return f'Invalid document type: {doc_type}.'
    return None


# ─── Composite validation helpers ────────────────────────────────────

def validate_booking_data(data, is_edit=False, existing_booking=None):
    """
    Validate a complete booking data dict. Returns a dict of field→error.

    Parameters:
        data: dict with keys matching Booking fields
        is_edit: True if editing an existing booking
        existing_booking: the existing Booking instance (for edit validation)
    """
    errors = {}

    # Ports
    err = validate_ports_different(data.get('origin_port'), data.get('destination_port'))
    if err:
        errors['__all__'] = err

    # Cargo ready date
    existing_date = existing_booking.cargo_ready_date if existing_booking else None
    err = validate_cargo_ready_date(data.get('cargo_ready_date'), existing_date)
    if err:
        errors['cargo_ready_date'] = err

    # Container count
    err = validate_container_count(data.get('container_count', 1))
    if err:
        errors['container_count'] = err

    # INCOTERMS
    err = validate_incoterms(data.get('incoterms'))
    if err:
        errors['incoterms'] = err

    return errors


def validate_booking_item_data(data):
    """
    Validate a single cargo item data dict. Returns a dict of field→error.
    """
    errors = {}

    # Description is required
    desc = data.get('description', '')
    if not desc or not str(desc).strip():
        errors['description'] = 'Description is required.'
    elif len(str(desc).strip()) > 500:
        errors['description'] = 'Description must not exceed 500 characters.'

    err = validate_quantity(data.get('quantity'))
    if err:
        errors['quantity'] = err

    err = validate_weight_kg(data.get('weight_kg'))
    if err:
        errors['weight_kg'] = err

    err = validate_volume_cbm(data.get('volume_cbm'))
    if err:
        errors['volume_cbm'] = err

    err = validate_dimensions(
        data.get('length_cm'), data.get('width_cm'), data.get('height_cm')
    )
    if err:
        errors['dimensions'] = err

    err = validate_hs_code(data.get('hs_code'))
    if err:
        errors['hs_code'] = err

    err = validate_hazardous_fields(
        data.get('is_hazardous', False),
        data.get('un_number', ''),
        data.get('imo_class', ''),
    )
    if err:
        errors['hazardous'] = err

    err = validate_country_code(data.get('country_of_origin'))
    if err:
        errors['country_of_origin'] = err

    err = validate_package_type(data.get('package_type'))
    if err:
        errors['package_type'] = err

    return errors
