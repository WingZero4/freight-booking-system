from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from .models import Booking, BookingItem, BookingDocument, Port, ContainerType
from .forms import BookingForm, BookingItemFormSet, BookingDocumentForm


def get_user_customer(user):
    """Return the customer associated with the user, or None for staff."""
    if hasattr(user, 'profile') and user.profile.customer:
        return user.profile.customer
    return None


def get_booking_for_user(booking_id, user):
    """Get a booking, checking that the user has permission to access it."""
    booking = get_object_or_404(Booking, id=booking_id)
    customer = get_user_customer(user)
    if customer and booking.customer != customer:
        raise Http404
    return booking


@login_required
def dashboard(request):
    """Dashboard with booking summary statistics"""
    customer = get_user_customer(request.user)
    if customer:
        bookings = Booking.objects.filter(customer=customer)
    else:
        bookings = Booking.objects.all()

    stats = {
        'total': bookings.count(),
        'draft': bookings.filter(status='DRAFT').count(),
        'submitted': bookings.filter(status='SUBMITTED').count(),
        'confirmed': bookings.filter(status='CONFIRMED').count(),
        'cancelled': bookings.filter(status='CANCELLED').count(),
    }
    recent_bookings = bookings[:5]

    return render(request, 'bookings/dashboard.html', {
        'stats': stats,
        'recent_bookings': recent_bookings,
    })


@login_required
def booking_list(request):
    """List bookings with filtering, sorting, and pagination"""
    customer = get_user_customer(request.user)
    if customer:
        bookings = Booking.objects.filter(customer=customer)
    else:
        bookings = Booking.objects.all()

    # Filtering
    status_filter = request.GET.get('status', '')
    if status_filter:
        bookings = bookings.filter(status=status_filter)

    search_query = request.GET.get('q', '')
    if search_query:
        bookings = bookings.filter(
            Q(booking_number__icontains=search_query) |
            Q(origin_port__code__icontains=search_query) |
            Q(origin_port__name__icontains=search_query) |
            Q(destination_port__code__icontains=search_query) |
            Q(destination_port__name__icontains=search_query)
        )

    # Sorting
    sort_by = request.GET.get('sort', '-created_at')
    allowed_sorts = {
        'booking_number', '-booking_number',
        'cargo_ready_date', '-cargo_ready_date',
        'created_at', '-created_at',
        'status', '-status',
    }
    if sort_by in allowed_sorts:
        bookings = bookings.order_by(sort_by)

    # View mode
    view_mode = request.GET.get('view', 'table')

    # Pagination
    paginator = Paginator(bookings, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'bookings/booking_list.html', {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'sort_by': sort_by,
        'view_mode': view_mode,
        'status_choices': Booking.STATUS_CHOICES,
    })


@login_required
def booking_create(request):
    """Create a new booking with cargo items"""
    customer = get_user_customer(request.user)
    if not customer:
        messages.error(request, 'You must be associated with a customer to create bookings.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = BookingForm(request.POST)
        formset = BookingItemFormSet(request.POST, prefix='items')

        if form.is_valid() and formset.is_valid():
            booking = form.save(commit=False)
            booking.customer = customer
            booking.created_by = request.user
            booking.save()

            formset.instance = booking
            formset.save()

            messages.success(request, f'Booking {booking.booking_number} created successfully!')
            return redirect('booking_detail', booking_id=booking.id)
    else:
        form = BookingForm()
        formset = BookingItemFormSet(prefix='items')

    return render(request, 'bookings/booking_form.html', {
        'form': form,
        'formset': formset,
        'is_edit': False,
    })


@login_required
def booking_edit(request, booking_id):
    """Edit a draft booking"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status != 'DRAFT':
        messages.error(request, 'Only draft bookings can be edited.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = BookingForm(request.POST, instance=booking)
        formset = BookingItemFormSet(request.POST, instance=booking, prefix='items')

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, f'Booking {booking.booking_number} updated successfully!')
            return redirect('booking_detail', booking_id=booking.id)
    else:
        form = BookingForm(instance=booking)
        formset = BookingItemFormSet(instance=booking, prefix='items')

    return render(request, 'bookings/booking_form.html', {
        'form': form,
        'formset': formset,
        'booking': booking,
        'is_edit': True,
    })


@login_required
def booking_detail(request, booking_id):
    """View booking details with document management"""
    booking = get_booking_for_user(booking_id, request.user)
    documents = booking.documents.all()
    document_form = BookingDocumentForm()

    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
        'documents': documents,
        'document_form': document_form,
    })


@login_required
def booking_submit(request, booking_id):
    """Submit a draft booking (POST performs action, GET shows confirmation)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status != 'DRAFT':
        messages.warning(request, 'This booking has already been submitted.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        booking.submit()
        messages.success(request, f'Booking {booking.booking_number} submitted successfully!')
        return redirect('booking_detail', booking_id=booking.id)

    return render(request, 'bookings/booking_submit_confirm.html', {
        'booking': booking,
    })


@login_required
def booking_cancel(request, booking_id):
    """Cancel a booking (DRAFT or SUBMITTED only, POST required)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status not in ['DRAFT', 'SUBMITTED']:
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        booking.cancel(user=request.user)
        messages.success(request, f'Booking {booking.booking_number} has been cancelled.')
        return redirect('booking_detail', booking_id=booking.id)

    return render(request, 'bookings/booking_cancel_confirm.html', {
        'booking': booking,
    })


@login_required
def booking_document_upload(request, booking_id):
    """Upload a document to a booking"""
    booking = get_booking_for_user(booking_id, request.user)

    if request.method == 'POST':
        form = BookingDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.booking = booking
            document.uploaded_by = request.user
            document.original_filename = request.FILES['file'].name
            document.file_size = request.FILES['file'].size
            document.save()
            messages.success(request, f'Document "{document.original_filename}" uploaded.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')

    return redirect('booking_detail', booking_id=booking.id)


@login_required
def booking_document_delete(request, booking_id, document_id):
    """Delete a document (only on DRAFT bookings)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status != 'DRAFT':
        messages.error(request, 'Documents can only be deleted on draft bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    document = get_object_or_404(BookingDocument, id=document_id, booking=booking)

    if request.method == 'POST':
        filename = document.original_filename
        document.file.delete()
        document.delete()
        messages.success(request, f'Document "{filename}" deleted.')

    return redirect('booking_detail', booking_id=booking.id)
