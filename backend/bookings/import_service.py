"""
Import service: orchestrates file parsing, LLM extraction, validation,
and booking creation for bulk file imports.
"""
import logging
import uuid
from datetime import date, datetime

from django.utils import timezone

from .models import Port, ContainerType, Booking, BookingItem, ImportLog, ImportBookingLog
from .forms import BookingForm, BookingItemForm
from .services import BookingService
from .file_parsers import parse_file, FileParseError
from .llm_client import extract_bookings_from_content, LLMExtractionError

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_BOOKINGS_PER_IMPORT = 50
ALLOWED_IMPORT_EXTENSIONS = {'csv', 'xlsx', 'pdf'}


class FileImportError(Exception):
    """Import-level error (file too large, wrong type, etc.)."""
    pass


def get_reference_data():
    """Fetch ports and container types for the LLM prompt.

    Also returns lookup dicts for efficient in-memory resolution.
    """
    ports_qs = Port.objects.filter(is_active=True).order_by('code')
    ct_qs = ContainerType.objects.all().order_by('code')

    ports_list = list(ports_qs.values_list('pk', 'code', 'name'))
    ct_list = list(ct_qs.values_list('pk', 'code', 'name', 'size_ft', 'capacity_cbm', 'max_payload_kg'))

    # Build lookup dicts for fast resolution (avoids N+1 queries)
    port_by_code = {}
    port_by_code_lower = {}
    port_by_name_lower = {}
    for pk, code, name in ports_list:
        port_by_code[code] = (pk, code)
        port_by_code_lower[code.lower()] = (pk, code)
        name_lower = name.lower()
        # Only store if unique name — skip ambiguous names
        if name_lower in port_by_name_lower:
            port_by_name_lower[name_lower] = None  # ambiguous
        else:
            port_by_name_lower[name_lower] = (pk, code)

    ct_by_code = {}
    ct_by_code_lower = {}
    ct_by_name_lower = {}
    ct_capacity = {}
    for pk, code, name, size_ft, capacity_cbm, max_payload_kg in ct_list:
        ct_by_code[code] = (pk, code)
        ct_by_code_lower[code.lower()] = (pk, code)
        name_lower = name.lower()
        if name_lower in ct_by_name_lower:
            ct_by_name_lower[name_lower] = None
        else:
            ct_by_name_lower[name_lower] = (pk, code)
        ct_capacity[pk] = {
            'code': code,
            'capacity_cbm': float(capacity_cbm) if capacity_cbm else None,
            'max_payload_kg': float(max_payload_kg) if max_payload_kg else None,
        }

    return {
        'ports': [{'code': code, 'name': name} for _, code, name in ports_list],
        'container_types': [
            {'code': code, 'name': name, 'size_ft': size_ft}
            for _, code, name, size_ft, _, _ in ct_list
        ],
        '_port_by_code': port_by_code,
        '_port_by_code_lower': port_by_code_lower,
        '_port_by_name_lower': port_by_name_lower,
        '_ct_by_code': ct_by_code,
        '_ct_by_code_lower': ct_by_code_lower,
        '_ct_by_name_lower': ct_by_name_lower,
        '_ct_capacity': ct_capacity,
    }


def validate_import_file(uploaded_file):
    """Validate the uploaded file before processing. Returns list of errors."""
    errors = []
    if uploaded_file.size > MAX_FILE_SIZE:
        size_mb = uploaded_file.size / (1024 * 1024)
        errors.append(f'File size ({size_mb:.1f} MB) exceeds the 5 MB limit.')

    name = uploaded_file.name or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if not ext:
        errors.append('File has no extension. Please use a CSV, XLSX, or PDF file.')
    elif ext not in ALLOWED_IMPORT_EXTENSIONS:
        errors.append(f'File type .{ext} is not supported. Use CSV, XLSX, or PDF.')

    return errors


def _resolve_port(code, ref_data):
    """Resolve a port code using in-memory lookup dicts. Zero DB queries."""
    if not code:
        return None
    # Exact match
    result = ref_data['_port_by_code'].get(code)
    if result:
        return result
    # Case-insensitive
    result = ref_data['_port_by_code_lower'].get(code.lower())
    if result:
        return result
    # Name match (only if unambiguous)
    result = ref_data['_port_by_name_lower'].get(code.lower())
    if result:
        return result
    return None


def _resolve_container_type(code, ref_data):
    """Resolve a container type using in-memory lookup dicts. Zero DB queries."""
    if not code:
        return None
    result = ref_data['_ct_by_code'].get(code)
    if result:
        return result
    result = ref_data['_ct_by_code_lower'].get(code.lower())
    if result:
        return result
    result = ref_data['_ct_by_name_lower'].get(code.lower())
    if result:
        return result
    return None


def _parse_date(value):
    """Try to parse a date string in various formats."""
    if not value:
        return None
    if isinstance(value, date):
        return value.strftime('%Y-%m-%d')

    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d',
                '%d-%m-%Y', '%m-%d-%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            continue
    return str(value).strip()


def _validate_booking_entry(entry, index, ref_data):
    """
    Validate a single booking entry from the LLM.
    Resolves codes to DB IDs using in-memory lookups and classifies
    as valid/warning/error.
    """
    booking_data = entry.get('booking', {})
    items_data = entry.get('items', [])
    issues = list(entry.get('issues', []))
    validation_errors = {}

    # Resolve origin port
    origin_code = booking_data.get('origin_port_code')
    origin_result = _resolve_port(origin_code, ref_data)
    if origin_result:
        booking_data['origin_port_id'] = origin_result[0]
        booking_data['origin_port_code'] = origin_result[1]
    elif origin_code:
        validation_errors['origin_port'] = f'Unknown port code: {origin_code}'
    else:
        validation_errors['origin_port'] = 'Required field missing'

    # Resolve destination port
    dest_code = booking_data.get('destination_port_code')
    dest_result = _resolve_port(dest_code, ref_data)
    if dest_result:
        booking_data['destination_port_id'] = dest_result[0]
        booking_data['destination_port_code'] = dest_result[1]
    elif dest_code:
        validation_errors['destination_port'] = f'Unknown port code: {dest_code}'
    else:
        validation_errors['destination_port'] = 'Required field missing'

    # Check same origin/destination
    if origin_result and dest_result and origin_result[0] == dest_result[0]:
        validation_errors['ports'] = 'Origin and destination cannot be the same'

    # Validate transport mode (before container, since container depends on mode)
    valid_modes = {'SEA_FCL', 'SEA_LCL', 'AIR', 'SEA_AIR', 'AIR_SEA', 'RAIL', 'TRUCK', 'MULTIMODAL'}
    mode = booking_data.get('transport_mode')
    if not mode or mode not in valid_modes:
        validation_errors['transport_mode'] = f'Invalid transport mode: {mode}'
        mode = 'SEA_FCL'  # Default for validation logic below

    # Resolve container type (required for Sea FCL only)
    ct_code = booking_data.get('container_type_code')
    if ct_code:
        ct_result = _resolve_container_type(ct_code, ref_data)
        if ct_result:
            booking_data['container_type_id'] = ct_result[0]
            booking_data['container_type_code'] = ct_result[1]
        else:
            validation_errors['container_type'] = f'Unknown container type: {ct_code}'
    elif mode == 'SEA_FCL':
        validation_errors['container_type'] = 'Container type is required for FCL shipments'
    # else: container_type is optional for non-FCL — no error

    # Parse and validate cargo ready date
    raw_date = booking_data.get('cargo_ready_date')
    parsed_date = _parse_date(raw_date)
    if parsed_date:
        booking_data['cargo_ready_date'] = parsed_date
    else:
        validation_errors['cargo_ready_date'] = 'Required field missing'

    # Validate container count (required for Sea FCL only)
    cc = booking_data.get('container_count')
    if mode == 'SEA_FCL':
        if cc is None:
            booking_data['container_count'] = 1
        elif not isinstance(cc, int) or cc < 1:
            try:
                booking_data['container_count'] = max(1, int(cc))
            except (ValueError, TypeError):
                booking_data['container_count'] = 1
                issues.append('Container count defaulted to 1')
    else:
        # Non-FCL: keep None if not provided
        if cc is not None:
            try:
                booking_data['container_count'] = max(1, int(cc))
            except (ValueError, TypeError):
                booking_data['container_count'] = None

    # Validate incoterms
    valid_incoterms = {
        'FOB', 'CFR', 'CIF', 'EXW', 'FCA', 'CPT', 'CIP',
        'DAP', 'DPU', 'DDP', 'FAS',
    }
    inco = booking_data.get('incoterms', 'FOB')
    if inco and inco.upper() in valid_incoterms:
        booking_data['incoterms'] = inco.upper()
    else:
        booking_data['incoterms'] = 'FOB'
        if inco:
            issues.append(f'Unknown incoterms "{inco}", defaulted to FOB')

    # Validate cargo items
    if not items_data:
        validation_errors['items'] = 'At least one cargo item is required'
    else:
        for i, item in enumerate(items_data):
            if not item.get('description'):
                validation_errors[f'item_{i}_description'] = f'Item {i+1}: description required'
            if not item.get('quantity') or (isinstance(item.get('quantity'), (int, float)) and item['quantity'] < 1):
                validation_errors[f'item_{i}_quantity'] = f'Item {i+1}: quantity must be >= 1'
            if not item.get('weight_kg') or (isinstance(item.get('weight_kg'), (int, float)) and item['weight_kg'] <= 0):
                validation_errors[f'item_{i}_weight'] = f'Item {i+1}: weight_kg must be > 0'

            # Default package_type
            valid_pkg = {'PALLET', 'CARTON', 'CRATE', 'DRUM', 'BAG', 'BUNDLE', 'PACKAGE', 'OTHER'}
            pkg = item.get('package_type', 'PACKAGE')
            if pkg not in valid_pkg:
                item['package_type'] = 'PACKAGE'
                issues.append(f'Item {i+1}: unknown package type "{pkg}", defaulted to PACKAGE')

    # CBM container recommendation check (uses in-memory ref_data — no DB query)
    if mode in ('SEA_FCL', 'RAIL', 'TRUCK', 'MULTIMODAL', 'SEA_AIR', 'AIR_SEA') and items_data:
        total_cbm = sum(
            float(item.get('volume_cbm') or 0) for item in items_data
        )
        ct_id = booking_data.get('container_type_id')
        ct_count = booking_data.get('container_count') or 1
        if total_cbm > 0 and ct_id:
            # Look up capacity from pre-loaded reference data
            ct_capacity_map = ref_data.get('_ct_capacity', {})
            ct_info = ct_capacity_map.get(ct_id)
            if ct_info and ct_info['capacity_cbm'] and ct_info['capacity_cbm'] > 0:
                import math
                needed = math.ceil(total_cbm / ct_info['capacity_cbm'])
                if ct_count < needed:
                    issues.append(
                        f'CBM check: {total_cbm:.1f} CBM needs at least {needed}x '
                        f'{ct_info["code"]} (capacity {ct_info["capacity_cbm"]} CBM each), '
                        f'but only {ct_count} selected'
                    )

    # Classify status
    has_errors = bool(validation_errors)
    has_warnings = bool(issues) and not has_errors
    if has_errors:
        status = 'error'
    elif has_warnings:
        status = 'warning'
    else:
        status = 'valid'

    return {
        'index': index,
        'row_reference': entry.get('row_reference', f'Entry {index + 1}'),
        'confidence': entry.get('confidence', 'medium'),
        'issues': issues,
        'validation_errors': validation_errors,
        'status': status,
        'booking_data': booking_data,
        'items_data': items_data,
    }


def analyze_file(uploaded_file, import_log=None):
    """
    Parse file, call LLM, validate results.

    Returns a dict suitable for Django session storage.
    If import_log is provided, updates it with extraction results
    and creates ImportBookingLog rows.
    """
    filename = uploaded_file.name

    # 1. Parse file content
    file_content = parse_file(uploaded_file, filename)

    # 2. Get reference data (also builds in-memory lookup dicts)
    reference_data = get_reference_data()

    # 3. Call LLM
    llm_result = extract_bookings_from_content(file_content, reference_data)

    # 4. Validate each booking
    raw_bookings = llm_result.get('bookings', [])

    truncated = False
    if len(raw_bookings) > MAX_BOOKINGS_PER_IMPORT:
        truncated = True
        raw_bookings = raw_bookings[:MAX_BOOKINGS_PER_IMPORT]

    validated_bookings = []
    for i, entry in enumerate(raw_bookings):
        validated = _validate_booking_entry(entry, i, reference_data)
        validated_bookings.append(validated)

    # 5. Build summary
    total = len(validated_bookings)
    valid = sum(1 for b in validated_bookings if b['status'] == 'valid')
    warnings = sum(1 for b in validated_bookings if b['status'] == 'warning')
    errors_count = sum(1 for b in validated_bookings if b['status'] == 'error')

    extraction_notes = llm_result.get('extraction_notes', '')
    if truncated:
        extraction_notes += (
            f' Note: File contained more than {MAX_BOOKINGS_PER_IMPORT} bookings. '
            f'Only the first {MAX_BOOKINGS_PER_IMPORT} are shown.'
        )

    # Populate import log if provided
    if import_log:
        import_log.extracted_count = total
        import_log.valid_count = valid
        import_log.warning_count = warnings
        import_log.error_count = errors_count
        import_log.extraction_notes = extraction_notes.strip()
        import_log.status = 'PREVIEWING'
        import_log.save(update_fields=[
            'extracted_count', 'valid_count', 'warning_count',
            'error_count', 'extraction_notes', 'status',
        ])

        for entry in validated_bookings:
            ImportBookingLog.objects.create(
                import_log=import_log,
                row_index=entry['index'],
                row_reference=entry.get('row_reference', ''),
                status=entry['status'].upper(),
                confidence=entry.get('confidence', 'medium'),
                validation_errors=entry.get('validation_errors', {}),
                warnings=entry.get('issues', []),
            )

    return {
        'import_id': str(import_log.import_id) if import_log else str(uuid.uuid4()),
        'filename': filename,
        'bookings': validated_bookings,
        'summary': {
            'total': total,
            'valid': valid,
            'warnings': warnings,
            'errors': errors_count,
        },
        'extraction_notes': extraction_notes.strip(),
    }


def create_bookings_from_import(import_data, selected_indices, customer, user,
                                request=None, import_log=None):
    """
    Create bookings from validated import data.

    Returns dict with 'created': [booking_numbers], 'failed': [{index, error}]
    If import_log is provided, updates ImportBookingLog rows and finalizes ImportLog.
    """
    results = {'created': [], 'failed': []}

    for idx in selected_indices:
        if idx < 0 or idx >= len(import_data['bookings']):
            continue

        booking_entry = import_data['bookings'][idx]

        if booking_entry['status'] == 'error':
            results['failed'].append({
                'index': idx,
                'error': 'Booking has validation errors and cannot be created.',
            })
            if import_log:
                ImportBookingLog.objects.filter(
                    import_log=import_log, row_index=idx,
                ).update(
                    was_selected=True,
                    status='CREATE_FAILED',
                    error_message='Booking has validation errors and cannot be created.',
                )
            continue

        try:
            booking = _create_single_booking(
                booking_entry, customer, user, request
            )
            results['created'].append(booking.booking_number)
            if import_log:
                ImportBookingLog.objects.filter(
                    import_log=import_log, row_index=idx,
                ).update(
                    was_selected=True,
                    status='CREATED',
                    booking=booking,
                )
        except Exception as e:
            logger.exception('Failed to create import booking #%d', idx)
            results['failed'].append({'index': idx, 'error': str(e)})
            if import_log:
                ImportBookingLog.objects.filter(
                    import_log=import_log, row_index=idx,
                ).update(
                    was_selected=True,
                    status='CREATE_FAILED',
                    error_message=str(e)[:1000],
                )

    # Finalize import log
    if import_log:
        # Mark unselected valid/warning rows as SKIPPED
        ImportBookingLog.objects.filter(
            import_log=import_log,
            was_selected=False,
            status__in=['VALID', 'WARNING'],
        ).update(status='SKIPPED')

        import_log.created_count = len(results['created'])
        import_log.failed_count = len(results['failed'])
        import_log.status = 'COMPLETED'
        import_log.completed_at = timezone.now()
        import_log.save(update_fields=[
            'created_count', 'failed_count', 'status', 'completed_at',
        ])

    return results


def _create_single_booking(booking_entry, customer, user, request):
    """Create a single booking from import data using BookingService."""
    bd = booking_entry['booking_data']
    items = booking_entry['items_data']

    # Build form data dict for BookingForm
    form_data = {
        'transport_mode': bd.get('transport_mode', ''),
        'origin_port': bd.get('origin_port_id', ''),
        'destination_port': bd.get('destination_port_id', ''),
        'cargo_ready_date': bd.get('cargo_ready_date', ''),
        'container_type': bd.get('container_type_id') or '',
        'container_count': bd.get('container_count') or '',
        'chargeable_weight_kg': bd.get('chargeable_weight_kg') or '',
        'flight_number': bd.get('flight_number') or '',
        'incoterms': bd.get('incoterms', 'FOB'),
        'incoterms_location': bd.get('incoterms_location', '') or '',
        'commodity_description': bd.get('commodity_description', '') or '',
        'is_hazardous': bd.get('is_hazardous', False),
        'external_reference': bd.get('external_reference', '') or '',
        'special_instructions': bd.get('special_instructions', '') or '',
    }

    # Build formset management data
    formset_data = {
        'items-TOTAL_FORMS': str(len(items)),
        'items-INITIAL_FORMS': '0',
        'items-MIN_NUM_FORMS': '1',
        'items-MAX_NUM_FORMS': '50',
    }

    for i, item in enumerate(items):
        prefix = f'items-{i}-'
        formset_data[f'{prefix}description'] = item.get('description', '')
        formset_data[f'{prefix}package_type'] = item.get('package_type', 'PACKAGE')
        formset_data[f'{prefix}quantity'] = str(item.get('quantity', 1))
        formset_data[f'{prefix}weight_kg'] = str(item.get('weight_kg', 0))

        # Optional fields
        for opt_field in ['hs_code', 'volume_cbm', 'length_cm', 'width_cm',
                          'height_cm', 'marks_and_numbers', 'un_number',
                          'imo_class', 'country_of_origin']:
            val = item.get(opt_field)
            if val is not None and val != '':
                formset_data[f'{prefix}{opt_field}'] = str(val)
            else:
                formset_data[f'{prefix}{opt_field}'] = ''

        formset_data[f'{prefix}is_hazardous'] = 'on' if item.get('is_hazardous') else ''

    combined_data = {**form_data, **formset_data}

    from django.forms import inlineformset_factory
    ItemFormSet = inlineformset_factory(
        Booking, BookingItem,
        form=BookingItemForm,
        extra=len(items),
        min_num=1,
        validate_min=True,
        can_delete=True,
    )

    form = BookingForm(combined_data)
    formset = ItemFormSet(combined_data, prefix='items')

    if not form.is_valid():
        error_msgs = '; '.join(
            f'{field}: {", ".join(errs)}'
            for field, errs in form.errors.items()
        )
        raise ValueError(f'Form validation failed: {error_msgs}')

    if not formset.is_valid():
        error_msgs = []
        for i, errs in enumerate(formset.errors):
            if errs:
                for field, msgs in errs.items():
                    error_msgs.append(f'Item {i+1} {field}: {", ".join(msgs)}')
        if formset.non_form_errors():
            error_msgs.extend(formset.non_form_errors())
        raise ValueError(f'Item validation failed: {"; ".join(error_msgs)}')

    booking = BookingService.create_booking(
        form, formset, customer, user,
        request=request, source_channel='CSV',
    )
    return booking


# ── Helpers for editable import preview ─────────────────────────────


def recalculate_summary(bookings):
    """Recalculate the summary counts from the bookings list."""
    total = len(bookings)
    valid = sum(1 for b in bookings if b['status'] == 'valid')
    warnings = sum(1 for b in bookings if b['status'] == 'warning')
    errors = sum(1 for b in bookings if b['status'] == 'error')
    return {
        'total': total,
        'valid': valid,
        'warnings': warnings,
        'errors': errors,
    }


def build_session_entry_from_form(form, formset, index, original_entry):
    """
    Build an updated session entry dict from validated BookingForm + formset.
    Called after form.is_valid() and formset.is_valid() both return True.

    Preserves original_entry's row_reference and confidence.
    """
    cd = form.cleaned_data

    origin_port = cd['origin_port']
    dest_port = cd['destination_port']
    container_type = cd.get('container_type')

    booking_data = {
        'transport_mode': cd['transport_mode'],
        'origin_port_id': origin_port.pk,
        'origin_port_code': origin_port.code,
        'destination_port_id': dest_port.pk,
        'destination_port_code': dest_port.code,
        'cargo_ready_date': cd['cargo_ready_date'].strftime('%Y-%m-%d'),
        'container_type_id': container_type.pk if container_type else None,
        'container_type_code': container_type.code if container_type else None,
        'container_count': cd.get('container_count'),
        'chargeable_weight_kg': str(cd['chargeable_weight_kg']) if cd.get('chargeable_weight_kg') else None,
        'flight_number': cd.get('flight_number') or '',
        'incoterms': cd['incoterms'],
        'incoterms_location': cd.get('incoterms_location') or '',
        'commodity_description': cd.get('commodity_description') or '',
        'is_hazardous': cd.get('is_hazardous', False),
        'external_reference': cd.get('external_reference') or '',
        'special_instructions': cd.get('special_instructions') or '',
        'service_type': cd.get('service_type') or '',
    }

    items_data = []
    for item_form in formset:
        if item_form.cleaned_data.get('DELETE'):
            continue
        if not item_form.cleaned_data.get('description'):
            continue
        icd = item_form.cleaned_data
        items_data.append({
            'description': icd.get('description', ''),
            'package_type': icd.get('package_type', 'PACKAGE'),
            'quantity': icd.get('quantity', 1),
            'weight_kg': float(icd.get('weight_kg', 0)),
            'hs_code': icd.get('hs_code') or '',
            'volume_cbm': float(icd['volume_cbm']) if icd.get('volume_cbm') else None,
            'length_cm': float(icd['length_cm']) if icd.get('length_cm') else None,
            'width_cm': float(icd['width_cm']) if icd.get('width_cm') else None,
            'height_cm': float(icd['height_cm']) if icd.get('height_cm') else None,
            'marks_and_numbers': icd.get('marks_and_numbers') or '',
            'is_hazardous': icd.get('is_hazardous', False),
            'un_number': icd.get('un_number') or '',
            'imo_class': icd.get('imo_class') or '',
            'country_of_origin': icd.get('country_of_origin') or '',
        })

    return {
        'index': index,
        'row_reference': original_entry.get('row_reference', f'Entry {index + 1}'),
        'confidence': original_entry.get('confidence', 'medium'),
        'issues': [],
        'validation_errors': {},
        'status': 'valid',
        'booking_data': booking_data,
        'items_data': items_data,
    }
