"""
Views for the LLM-powered file import feature.
"""
import logging
import uuid

from decimal import Decimal, InvalidOperation

from django.forms import inlineformset_factory
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .models import Customer, Booking, BookingItem, ImportLog, ImportBookingLog
from .forms import BookingForm, BookingItemForm
from .views import get_user_customer, require_feature
from .tenant import get_user_organization
from .import_service import (
    validate_import_file, analyze_file, create_bookings_from_import,
    build_session_entry_from_form, recalculate_summary,
    FileImportError, MAX_BOOKINGS_PER_IMPORT,
)
from .file_parsers import FileParseError
from .llm_client import LLMExtractionError

logger = logging.getLogger(__name__)


def _resolve_import_customer(request):
    """Resolve customer for import. Returns (customer, is_staff, customers_list).

    For customer users: returns their own customer.
    For staff users: returns None initially (must be selected via form).
    """
    customer = get_user_customer(request.user)
    is_staff = customer is None
    if is_staff:
        org = get_user_organization(request.user)
        customers_list = Customer.objects.filter(
            is_active=True, organization=org,
        ).order_by('name') if org else Customer.objects.none()
    else:
        customers_list = None
    return customer, is_staff, customers_list


@login_required
@require_feature('enable_import')
def booking_import(request):
    """
    Step 1 (GET): Show upload form.
    Step 2 (POST): Parse file, call LLM, store in session, redirect to preview.
    """
    customer, is_staff, customers_list = _resolve_import_customer(request)

    if request.method == 'POST':
        # Resolve customer for staff
        if is_staff:
            customer_id = request.POST.get('customer')
            org = get_user_organization(request.user)
            try:
                customer = Customer.objects.get(
                    pk=customer_id, is_active=True, organization=org,
                )
            except (Customer.DoesNotExist, ValueError, TypeError):
                messages.error(request, 'Please select a valid customer.')
                return render(request, 'bookings/import_upload.html', {
                    'is_staff_import': True,
                    'customers': customers_list,
                    'selected_customer': customer_id,
                })

        # Preserve staff customer selection for re-renders on error
        staff_customer_id = request.POST.get('customer') if is_staff else None

        uploaded_file = request.FILES.get('import_file')
        if not uploaded_file:
            messages.error(request, 'Please select a file to import.')
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })

        # Validate file
        file_errors = validate_import_file(uploaded_file)
        if file_errors:
            for err in file_errors:
                messages.error(request, err)
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })

        auto_create = request.POST.get('auto_create') == 'on'

        # Create ImportLog record
        import_log = ImportLog.objects.create(
            import_id=uuid.uuid4(),
            uploaded_by=request.user,
            customer=customer,
            filename=uploaded_file.name,
            file_size=uploaded_file.size,
            status='ANALYZING',
            ip_address=request.META.get('REMOTE_ADDR', '') or None,
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )

        try:
            import_data = analyze_file(uploaded_file, import_log=import_log)
        except FileParseError as e:
            import_log.status = 'FAILED'
            import_log.error_message = f'Could not parse file: {e}'
            import_log.completed_at = timezone.now()
            import_log.save(update_fields=['status', 'error_message', 'completed_at'])
            messages.error(request, f'Could not parse file: {e}')
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except LLMExtractionError as e:
            import_log.status = 'FAILED'
            import_log.error_message = f'AI analysis failed: {e}'
            import_log.completed_at = timezone.now()
            import_log.save(update_fields=['status', 'error_message', 'completed_at'])
            messages.error(request, f'AI analysis failed: {e}')
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except FileImportError as e:
            import_log.status = 'FAILED'
            import_log.error_message = str(e)
            import_log.completed_at = timezone.now()
            import_log.save(update_fields=['status', 'error_message', 'completed_at'])
            messages.error(request, str(e))
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except Exception:
            logger.exception('Unexpected error during file import analysis')
            import_log.status = 'FAILED'
            import_log.error_message = 'An unexpected error occurred during analysis.'
            import_log.completed_at = timezone.now()
            import_log.save(update_fields=['status', 'error_message', 'completed_at'])
            messages.error(
                request,
                'An unexpected error occurred during analysis. Please try again.',
            )
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })

        if not import_data['bookings']:
            import_log.status = 'FAILED'
            import_log.error_message = 'No bookings could be extracted from the file.'
            import_log.completed_at = timezone.now()
            import_log.save(update_fields=['status', 'error_message', 'completed_at'])
            messages.warning(
                request,
                'No bookings could be extracted from the file. '
                'Please check the file format and try again.',
            )
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })

        # Store in session (include customer_id for staff imports)
        request.session['import_preview'] = import_data
        request.session['import_log_id'] = import_log.pk
        if is_staff:
            request.session['import_customer_id'] = customer.pk

        # Auto-create path (valid only — skip warnings for safety)
        if auto_create:
            valid_indices = [
                i for i, b in enumerate(import_data['bookings'])
                if b['status'] == 'valid'
            ]
            if valid_indices:
                results = create_bookings_from_import(
                    import_data, valid_indices, customer, request.user, request,
                    import_log=import_log,
                )
                # Clear session
                request.session.pop('import_preview', None)
                request.session.pop('import_customer_id', None)
                request.session.pop('import_log_id', None)

                if results['created']:
                    messages.success(
                        request,
                        f'Successfully created {len(results["created"])} '
                        f'booking(s) as DRAFT: {", ".join(results["created"])}',
                    )
                if results['failed']:
                    messages.warning(
                        request,
                        f'{len(results["failed"])} booking(s) could not be created.',
                    )
                return redirect('booking_list')
            else:
                messages.warning(
                    request,
                    'No valid bookings found for auto-creation. Showing preview.',
                )

        return redirect('booking_import_preview')

    # Clear stale import session data on fresh page load
    stale_log_id = request.session.pop('import_log_id', None)
    if stale_log_id:
        try:
            stale_log = ImportLog.objects.get(pk=stale_log_id, status='PREVIEWING')
            stale_log.status = 'FAILED'
            stale_log.error_message = 'Import abandoned by user.'
            stale_log.completed_at = timezone.now()
            stale_log.save(update_fields=['status', 'error_message', 'completed_at'])
        except ImportLog.DoesNotExist:
            pass
    request.session.pop('import_preview', None)
    request.session.pop('import_customer_id', None)

    return render(request, 'bookings/import_upload.html', {
        'is_staff_import': is_staff,
        'customers': customers_list,
    })


@login_required
@require_feature('enable_import')
def booking_import_preview(request):
    """Show preview of extracted bookings. User selects which to create."""
    customer, is_staff, _ = _resolve_import_customer(request)

    # For staff, resolve customer from session
    if is_staff:
        customer_id = request.session.get('import_customer_id')
        if customer_id:
            try:
                org = get_user_organization(request.user)
                customer = Customer.objects.get(
                    pk=customer_id, is_active=True, organization=org,
                )
            except Customer.DoesNotExist:
                messages.error(request, 'Selected customer no longer exists.')
                return redirect('booking_import')
        else:
            messages.error(request, 'No customer selected. Please start over.')
            return redirect('booking_import')

    import_data = request.session.get('import_preview')
    if not import_data:
        messages.error(
            request,
            'No import data found. Please upload a file first.',
        )
        return redirect('booking_import')

    return render(request, 'bookings/import_preview.html', {
        'import_data': import_data,
        'import_customer': customer if is_staff else None,
    })


@login_required
@require_feature('enable_import')
def booking_import_confirm(request):
    """Create selected bookings from the preview."""
    customer, is_staff, _ = _resolve_import_customer(request)

    # For staff, resolve customer from session
    if is_staff:
        customer_id = request.session.get('import_customer_id')
        if customer_id:
            try:
                org = get_user_organization(request.user)
                customer = Customer.objects.get(
                    pk=customer_id, is_active=True, organization=org,
                )
            except Customer.DoesNotExist:
                messages.error(request, 'Selected customer no longer exists.')
                return redirect('booking_import')
        else:
            messages.error(request, 'No customer selected. Please start over.')
            return redirect('booking_import')

    if request.method != 'POST':
        return redirect('booking_import')

    import_data = request.session.get('import_preview')
    if not import_data:
        messages.error(
            request,
            'Import session expired. Please upload the file again.',
        )
        return redirect('booking_import')

    # Verify import_id to prevent stale/cross-tab submissions
    submitted_id = request.POST.get('import_id', '')
    session_id = import_data.get('import_id', '')
    if not submitted_id or submitted_id != session_id:
        messages.error(
            request,
            'Import session mismatch. Please upload the file again.',
        )
        return redirect('booking_import')

    # Get selected booking indices
    selected = request.POST.getlist('selected_bookings')
    try:
        selected_indices = [int(i) for i in selected]
    except (ValueError, TypeError):
        messages.error(request, 'Invalid selection.')
        return redirect('booking_import_preview')

    if not selected_indices:
        messages.warning(request, 'No bookings selected for creation.')
        return redirect('booking_import_preview')

    # Filter to valid range
    max_idx = len(import_data['bookings']) - 1
    selected_indices = [i for i in selected_indices if 0 <= i <= max_idx]

    if not selected_indices:
        messages.warning(request, 'No valid bookings selected for creation.')
        return redirect('booking_import_preview')

    # Retrieve import log from session
    import_log = None
    import_log_id = request.session.get('import_log_id')
    if import_log_id:
        try:
            import_log = ImportLog.objects.get(pk=import_log_id)
        except ImportLog.DoesNotExist:
            pass

    results = create_bookings_from_import(
        import_data, selected_indices, customer, request.user, request,
        import_log=import_log,
    )

    # Clear session
    request.session.pop('import_preview', None)
    request.session.pop('import_customer_id', None)
    request.session.pop('import_log_id', None)

    if results['created']:
        messages.success(
            request,
            f'Successfully created {len(results["created"])} '
            f'booking(s) as DRAFT: {", ".join(results["created"])}',
        )
    if results['failed']:
        for fail in results['failed']:
            messages.error(
                request,
                f'Booking #{fail["index"] + 1}: {fail["error"]}',
            )

    return redirect('booking_list')


@login_required
@require_feature('enable_import')
def booking_import_edit(request, index):
    """Edit a single booking entry from the import preview."""
    customer, is_staff, _ = _resolve_import_customer(request)

    # For staff, resolve customer from session
    if is_staff:
        customer_id = request.session.get('import_customer_id')
        if customer_id:
            try:
                org = get_user_organization(request.user)
                customer = Customer.objects.get(
                    pk=customer_id, is_active=True, organization=org,
                )
            except Customer.DoesNotExist:
                messages.error(request, 'Selected customer no longer exists.')
                return redirect('booking_import')
        else:
            messages.error(request, 'No customer selected. Please start over.')
            return redirect('booking_import')

    import_data = request.session.get('import_preview')
    if not import_data:
        messages.error(request, 'No import data found. Please upload a file first.')
        return redirect('booking_import')

    if index < 0 or index >= len(import_data['bookings']):
        messages.error(request, 'Invalid booking index.')
        return redirect('booking_import_preview')

    entry = import_data['bookings'][index]
    bd = entry['booking_data']
    items = entry.get('items_data', [])

    if request.method == 'POST':
        form = BookingForm(request.POST)
        ItemFormSet = inlineformset_factory(
            Booking, BookingItem,
            form=BookingItemForm,
            extra=0,
            min_num=1,
            validate_min=True,
            can_delete=True,
            max_num=50,
        )
        formset = ItemFormSet(request.POST, prefix='items')

        if form.is_valid() and formset.is_valid():
            updated_entry = build_session_entry_from_form(
                form, formset, index, entry,
            )

            import_data['bookings'][index] = updated_entry
            import_data['summary'] = recalculate_summary(import_data['bookings'])
            request.session['import_preview'] = import_data
            request.session.modified = True

            # Update ImportBookingLog if exists
            import_log_id = request.session.get('import_log_id')
            if import_log_id:
                ImportBookingLog.objects.filter(
                    import_log_id=import_log_id,
                    row_index=index,
                ).update(
                    status=updated_entry['status'].upper(),
                    validation_errors=updated_entry['validation_errors'],
                    warnings=updated_entry['issues'],
                )

            messages.success(request, f'Booking #{index + 1} updated successfully.')
            return redirect('booking_import_preview')
    else:
        # Pre-fill form from session booking_data
        initial = {
            'transport_mode': bd.get('transport_mode'),
            'origin_port': bd.get('origin_port_id'),
            'destination_port': bd.get('destination_port_id'),
            'cargo_ready_date': bd.get('cargo_ready_date'),
            'container_type': bd.get('container_type_id'),
            'container_count': bd.get('container_count'),
            'incoterms': bd.get('incoterms', 'FOB'),
            'incoterms_location': bd.get('incoterms_location') or '',
            'commodity_description': bd.get('commodity_description') or '',
            'is_hazardous': bd.get('is_hazardous', False),
            'external_reference': bd.get('external_reference') or '',
            'special_instructions': bd.get('special_instructions') or '',
            'service_type': bd.get('service_type') or '',
            'move_type': bd.get('move_type') or '',
        }

        # Air freight fields
        cw = bd.get('chargeable_weight_kg')
        if cw:
            try:
                initial['chargeable_weight_kg'] = Decimal(str(cw))
            except (InvalidOperation, TypeError):
                pass
        initial['flight_number'] = bd.get('flight_number') or ''

        form = BookingForm(initial=initial)

        # Build initial items for formset
        initial_items = []
        for item in items:
            item_init = {
                'description': item.get('description', ''),
                'package_type': item.get('package_type', 'PACKAGE'),
                'quantity': item.get('quantity', 1),
                'weight_kg': item.get('weight_kg', 0),
                'hs_code': item.get('hs_code') or '',
                'marks_and_numbers': item.get('marks_and_numbers') or '',
                'is_hazardous': item.get('is_hazardous', False),
                'un_number': item.get('un_number') or '',
                'imo_class': item.get('imo_class') or '',
                'country_of_origin': item.get('country_of_origin') or '',
            }
            for field in ('volume_cbm', 'length_cm', 'width_cm', 'height_cm'):
                val = item.get(field)
                if val:
                    try:
                        item_init[field] = Decimal(str(val))
                    except (InvalidOperation, TypeError):
                        pass
            initial_items.append(item_init)

        num_items = max(len(initial_items), 1)
        ItemFormSet = inlineformset_factory(
            Booking, BookingItem,
            form=BookingItemForm,
            extra=num_items,
            min_num=1,
            validate_min=True,
            can_delete=True,
        )
        formset = ItemFormSet(
            prefix='items',
            initial=initial_items,
            queryset=BookingItem.objects.none(),
        )

    return render(request, 'bookings/import_edit.html', {
        'form': form,
        'formset': formset,
        'entry': entry,
        'entry_index': index,
        'import_data': import_data,
    })
