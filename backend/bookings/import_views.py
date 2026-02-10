"""
Views for the LLM-powered file import feature.
"""
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .views import get_user_customer
from .import_service import (
    validate_import_file, analyze_file, create_bookings_from_import,
    FileImportError, MAX_BOOKINGS_PER_IMPORT,
)
from .file_parsers import FileParseError
from .llm_client import LLMExtractionError

logger = logging.getLogger(__name__)


@login_required
def booking_import(request):
    """
    Step 1 (GET): Show upload form.
    Step 2 (POST): Parse file, call LLM, store in session, redirect to preview.
    """
    customer = get_user_customer(request.user)
    if not customer:
        messages.error(
            request,
            'You must be associated with a customer to import bookings.',
        )
        return redirect('dashboard')

    if request.method == 'POST':
        uploaded_file = request.FILES.get('import_file')
        if not uploaded_file:
            messages.error(request, 'Please select a file to import.')
            return render(request, 'bookings/import_upload.html')

        # Validate file
        file_errors = validate_import_file(uploaded_file)
        if file_errors:
            for err in file_errors:
                messages.error(request, err)
            return render(request, 'bookings/import_upload.html')

        auto_create = request.POST.get('auto_create') == 'on'

        try:
            import_data = analyze_file(uploaded_file)
        except FileParseError as e:
            messages.error(request, f'Could not parse file: {e}')
            return render(request, 'bookings/import_upload.html')
        except LLMExtractionError as e:
            messages.error(request, f'AI analysis failed: {e}')
            return render(request, 'bookings/import_upload.html')
        except FileImportError as e:
            messages.error(request, str(e))
            return render(request, 'bookings/import_upload.html')
        except Exception:
            logger.exception('Unexpected error during file import analysis')
            messages.error(
                request,
                'An unexpected error occurred during analysis. Please try again.',
            )
            return render(request, 'bookings/import_upload.html')

        if not import_data['bookings']:
            messages.warning(
                request,
                'No bookings could be extracted from the file. '
                'Please check the file format and try again.',
            )
            return render(request, 'bookings/import_upload.html')

        # Store in session
        request.session['import_preview'] = import_data

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

    return render(request, 'bookings/import_upload.html')


@login_required
def booking_import_preview(request):
    """Show preview of extracted bookings. User selects which to create."""
    customer = get_user_customer(request.user)
    if not customer:
        messages.error(request, 'You must be associated with a customer to import bookings.')
        return redirect('dashboard')

    import_data = request.session.get('import_preview')
    if not import_data:
        messages.error(
            request,
            'No import data found. Please upload a file first.',
        )
        return redirect('booking_import')

    return render(request, 'bookings/import_preview.html', {
        'import_data': import_data,
    })


@login_required
def booking_import_confirm(request):
    """Create selected bookings from the preview."""
    customer = get_user_customer(request.user)
    if not customer:
        messages.error(request, 'You must be associated with a customer to import bookings.')
        return redirect('dashboard')

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

    results = create_bookings_from_import(
        import_data, selected_indices, customer, request.user, request,
    )

    # Clear session
    request.session.pop('import_preview', None)

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
