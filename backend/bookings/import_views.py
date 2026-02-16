"""
Views for the LLM-powered file import feature.
"""
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Customer
from .views import get_user_customer
from .import_service import (
    validate_import_file, analyze_file, create_bookings_from_import,
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
    customers_list = Customer.objects.filter(is_active=True).order_by('name') if is_staff else None
    return customer, is_staff, customers_list


@login_required
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
            try:
                customer = Customer.objects.get(pk=customer_id, is_active=True)
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

        try:
            import_data = analyze_file(uploaded_file)
        except FileParseError as e:
            messages.error(request, f'Could not parse file: {e}')
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except LLMExtractionError as e:
            messages.error(request, f'AI analysis failed: {e}')
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except FileImportError as e:
            messages.error(request, str(e))
            return render(request, 'bookings/import_upload.html', {
                'is_staff_import': is_staff,
                'customers': customers_list,
                'selected_customer': staff_customer_id,
            })
        except Exception:
            logger.exception('Unexpected error during file import analysis')
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
                )
                # Clear session
                request.session.pop('import_preview', None)
                request.session.pop('import_customer_id', None)

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
    request.session.pop('import_preview', None)
    request.session.pop('import_customer_id', None)

    return render(request, 'bookings/import_upload.html', {
        'is_staff_import': is_staff,
        'customers': customers_list,
    })


@login_required
def booking_import_preview(request):
    """Show preview of extracted bookings. User selects which to create."""
    customer, is_staff, _ = _resolve_import_customer(request)

    # For staff, resolve customer from session
    if is_staff:
        customer_id = request.session.get('import_customer_id')
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, is_active=True)
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
def booking_import_confirm(request):
    """Create selected bookings from the preview."""
    customer, is_staff, _ = _resolve_import_customer(request)

    # For staff, resolve customer from session
    if is_staff:
        customer_id = request.session.get('import_customer_id')
        if customer_id:
            try:
                customer = Customer.objects.get(pk=customer_id, is_active=True)
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

    results = create_bookings_from_import(
        import_data, selected_indices, customer, request.user, request,
    )

    # Clear session
    request.session.pop('import_preview', None)
    request.session.pop('import_customer_id', None)

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
