import csv
from functools import wraps
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Avg, F
from django.http import FileResponse, Http404, HttpResponse
from django.utils import timezone

from .models import Booking, BookingItem, BookingDocument, Party, BookingParty, AuditLog
from .forms import (
    BookingForm, BookingItemFormSet, BookingDocumentForm,
    PartyForm, BookingPartySelectForm,
    CarrierDetailsForm, RejectBookingForm,
    MarkInTransitForm, CompleteBookingForm, CancelConfirmedForm,
)
from .services import BookingService


def get_user_customer(user):
    """Return the customer associated with the user, or None for staff."""
    try:
        profile = user.profile
        if profile.customer:
            return profile.customer
    except user.__class__.profile.RelatedObjectDoesNotExist:
        pass
    return None


def get_booking_for_user(booking_id, user):
    """Get a booking, checking that the user has permission to access it."""
    booking = get_object_or_404(
        Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port', 'container_type'
        ),
        id=booking_id,
    )
    customer = get_user_customer(user)
    if customer and booking.customer != customer:
        raise Http404
    return booking


def staff_required(view_func):
    """Decorator: requires login AND staff user (no customer association)."""
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        customer = get_user_customer(request.user)
        if customer is not None:
            messages.error(request, 'You do not have permission to access this page.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── Dashboard ────────────────────────────────────────────────────────

@login_required
def dashboard(request):
    """Dashboard with booking summary statistics"""
    customer = get_user_customer(request.user)

    # Staff users get the operations dashboard
    if customer is None:
        return redirect('ops_dashboard')

    bookings = Booking.objects.filter(customer=customer)

    stats = {
        'total': bookings.count(),
        'draft': bookings.filter(status='DRAFT').count(),
        'submitted': bookings.filter(status='SUBMITTED').count(),
        'confirmed': bookings.filter(status='CONFIRMED').count(),
        'in_transit': bookings.filter(status='IN_TRANSIT').count(),
        'completed': bookings.filter(status='COMPLETED').count(),
        'cancelled': bookings.filter(status='CANCELLED').count(),
    }
    recent_bookings = bookings.select_related(
        'customer', 'origin_port', 'destination_port', 'container_type'
    )[:5]

    return render(request, 'bookings/dashboard.html', {
        'stats': stats,
        'recent_bookings': recent_bookings,
    })


# ─── Booking list ─────────────────────────────────────────────────────

@login_required
def booking_list(request):
    """List bookings with filtering, sorting, and pagination"""
    customer = get_user_customer(request.user)
    if customer:
        bookings = Booking.objects.filter(customer=customer)
    else:
        bookings = Booking.objects.all()

    bookings = bookings.select_related(
        'customer', 'origin_port', 'destination_port', 'container_type'
    )

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
            Q(destination_port__name__icontains=search_query) |
            Q(external_reference__icontains=search_query)
        )

    # Date range filter
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    if date_from:
        bookings = bookings.filter(created_at__date__gte=date_from)
    if date_to:
        bookings = bookings.filter(created_at__date__lte=date_to)

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
        'date_from': date_from,
        'date_to': date_to,
        'sort_by': sort_by,
        'view_mode': view_mode,
        'status_choices': Booking.STATUS_CHOICES,
    })


# ─── Booking CRUD ─────────────────────────────────────────────────────

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
            booking = BookingService.create_booking(
                form, formset, customer, request.user, request=request,
            )
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
            BookingService.update_booking(
                booking, form, formset, request.user, request=request,
            )
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
    """View booking details with tabs: Overview, Cargo, Parties, Documents, Activity"""
    booking = get_booking_for_user(booking_id, request.user)
    customer = get_user_customer(request.user)

    documents = booking.documents.all()
    document_form = BookingDocumentForm()

    parties = booking.booking_parties.select_related('party').all()
    party_select_form = None
    active_statuses = ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT')
    if customer and booking.status in active_statuses:
        party_select_form = BookingPartySelectForm(customer)
    elif not customer and booking.status in active_statuses:
        # Staff can also manage parties — use booking's customer for party list
        party_select_form = BookingPartySelectForm(booking.customer)

    audit_logs = booking.audit_logs.select_related('performed_by').all()[:20]

    return render(request, 'bookings/booking_detail.html', {
        'booking': booking,
        'documents': documents,
        'document_form': document_form,
        'parties': parties,
        'party_select_form': party_select_form,
        'audit_logs': audit_logs,
        'active_tab': request.GET.get('tab', 'overview'),
    })


# ─── Status transitions ──────────────────────────────────────────────

@login_required
def booking_submit(request, booking_id):
    """Submit a draft booking (POST performs action, GET shows confirmation)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status != 'DRAFT':
        messages.warning(request, 'This booking has already been submitted.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        try:
            BookingService.submit_booking(booking, request.user, request=request)
            messages.success(request, f'Booking {booking.booking_number} submitted successfully!')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('booking_detail', booking_id=booking.id)

    return render(request, 'bookings/booking_submit_confirm.html', {
        'booking': booking,
    })


@login_required
def booking_cancel(request, booking_id):
    """Cancel a booking (DRAFT/SUBMITTED for customers, CONFIRMED for staff)"""
    booking = get_booking_for_user(booking_id, request.user)
    customer = get_user_customer(request.user)

    # Customers can cancel DRAFT/SUBMITTED; staff can also cancel CONFIRMED
    if customer and booking.status not in ('DRAFT', 'SUBMITTED'):
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking_detail', booking_id=booking.id)
    if not customer and booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED'):
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking_detail', booking_id=booking.id)

    # Confirmed bookings require a cancellation reason (staff-only)
    if booking.status == 'CONFIRMED':
        if request.method == 'POST':
            form = CancelConfirmedForm(request.POST)
            if form.is_valid():
                try:
                    BookingService.cancel_booking(
                        booking, request.user,
                        reason=form.cleaned_data['reason'],
                        request=request,
                    )
                    messages.success(request, f'Booking {booking.booking_number} has been cancelled.')
                    return redirect('booking_detail', booking_id=booking.id)
                except ValueError as e:
                    messages.error(request, str(e))
        else:
            form = CancelConfirmedForm()
        return render(request, 'bookings/ops/cancel_confirmed.html', {
            'booking': booking,
            'form': form,
        })

    # DRAFT/SUBMITTED — simple confirmation
    if request.method == 'POST':
        try:
            BookingService.cancel_booking(booking, request.user, request=request)
            messages.success(request, f'Booking {booking.booking_number} has been cancelled.')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('booking_detail', booking_id=booking.id)

    return render(request, 'bookings/booking_cancel_confirm.html', {
        'booking': booking,
    })


@login_required
def booking_resubmit(request, booking_id):
    """Return a REJECTED booking to DRAFT for revision (customer action)."""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status != 'REJECTED':
        messages.error(request, 'Only rejected bookings can be resubmitted.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        try:
            BookingService.resubmit_booking(booking, request.user, request=request)
            messages.success(request, f'Booking {booking.booking_number} returned to draft. You can now edit and resubmit.')
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('booking_detail', booking_id=booking.id)

    return redirect('booking_detail', booking_id=booking.id)


# ─── Documents ────────────────────────────────────────────────────────

@login_required
def booking_document_upload(request, booking_id):
    """Upload a document to a booking (DRAFT or SUBMITTED only)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
        messages.error(request, 'Documents can only be uploaded to active bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = BookingDocumentForm(request.POST, request.FILES)
        try:
            BookingService.upload_document(booking, form, request.user, request=request)
            messages.success(request, 'Document uploaded successfully.')
        except ValueError as e:
            if form.errors:
                for field, errors in form.errors.items():
                    for error in errors:
                        messages.error(request, f'{error}')
            else:
                messages.error(request, str(e))

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
        try:
            BookingService.delete_document(booking, document, request.user, request=request)
            messages.success(request, 'Document deleted.')
        except ValueError as e:
            messages.error(request, str(e))

    return redirect('booking_detail', booking_id=booking.id)


@login_required
def booking_document_download(request, booking_id, document_id):
    """Download a document with authentication and permission check."""
    booking = get_booking_for_user(booking_id, request.user)
    document = get_object_or_404(BookingDocument, id=document_id, booking=booking)
    return FileResponse(
        document.file.open('rb'),
        as_attachment=True,
        filename=document.original_filename,
    )


# ─── Parties (address book) ──────────────────────────────────────────

@login_required
def party_list(request):
    """List all parties in the customer's address book"""
    customer = get_user_customer(request.user)
    if not customer:
        # Staff can see all parties
        parties = Party.objects.filter(is_active=True).select_related('customer')
    else:
        parties = Party.objects.filter(customer=customer, is_active=True)

    role_filter = request.GET.get('role', '')
    if role_filter:
        parties = parties.filter(role=role_filter)

    search = request.GET.get('q', '')
    if search:
        parties = parties.filter(
            Q(company_name__icontains=search) |
            Q(contact_name__icontains=search) |
            Q(email__icontains=search)
        )

    paginator = Paginator(parties, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'bookings/party_list.html', {
        'page_obj': page_obj,
        'role_filter': role_filter,
        'search_query': search,
        'role_choices': Party.ROLE_CHOICES,
    })


@login_required
def party_create(request):
    """Create a new address book party"""
    customer = get_user_customer(request.user)
    if not customer:
        messages.error(request, 'You must be associated with a customer to manage parties.')
        return redirect('dashboard')

    if request.method == 'POST':
        form = PartyForm(request.POST)
        if form.is_valid():
            party = form.save(commit=False)
            party.customer = customer
            party.save()
            messages.success(request, f'Party "{party.company_name}" created.')
            return redirect('party_list')
    else:
        form = PartyForm()

    return render(request, 'bookings/party_form.html', {
        'form': form,
        'is_edit': False,
    })


@login_required
def party_edit(request, party_id):
    """Edit an address book party"""
    customer = get_user_customer(request.user)
    party = get_object_or_404(Party, id=party_id)

    if customer and party.customer != customer:
        raise Http404

    if request.method == 'POST':
        form = PartyForm(request.POST, instance=party)
        if form.is_valid():
            form.save()
            messages.success(request, f'Party "{party.company_name}" updated.')
            return redirect('party_list')
    else:
        form = PartyForm(instance=party)

    return render(request, 'bookings/party_form.html', {
        'form': form,
        'party': party,
        'is_edit': True,
    })


@login_required
def party_delete(request, party_id):
    """Deactivate an address book party"""
    customer = get_user_customer(request.user)
    party = get_object_or_404(Party, id=party_id)

    if customer and party.customer != customer:
        raise Http404

    if request.method == 'POST':
        party.is_active = False
        party.save()
        messages.success(request, f'Party "{party.company_name}" removed from address book.')

    return redirect('party_list')


# ─── Booking party assignment ─────────────────────────────────────────

@login_required
def booking_party_add(request, booking_id):
    """Add a party from the address book to a booking"""
    booking = get_booking_for_user(booking_id, request.user)
    customer = get_user_customer(request.user)

    # Both customers and staff can manage parties
    party_customer = customer or booking.customer

    if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
        messages.error(request, 'Parties can only be added to active bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = BookingPartySelectForm(party_customer, request.POST)
        if form.is_valid():
            party = form.cleaned_data['party']
            role = form.cleaned_data['role']

            # Check if role already assigned
            if booking.booking_parties.filter(role=role).exists():
                messages.error(request, f'A {dict(BookingParty.ROLE_CHOICES).get(role)} is already assigned to this booking.')
            else:
                try:
                    BookingService.add_party_to_booking(
                        booking, party, role=role,
                        user=request.user, request=request,
                    )
                    messages.success(request, f'{party.company_name} added as {dict(BookingParty.ROLE_CHOICES).get(role)}.')
                except ValueError as e:
                    messages.error(request, str(e))

    return redirect('booking_detail', booking_id=booking.id)


@login_required
def booking_party_remove(request, booking_id, booking_party_id):
    """Remove a party assignment from a booking"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'IN_TRANSIT'):
        messages.error(request, 'Parties can only be removed from active bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    booking_party = get_object_or_404(BookingParty, id=booking_party_id, booking=booking)

    if request.method == 'POST':
        try:
            BookingService.remove_party_from_booking(
                booking, booking_party, user=request.user, request=request,
            )
            messages.success(request, 'Party removed from booking.')
        except ValueError as e:
            messages.error(request, str(e))

    return redirect('booking_detail', booking_id=booking.id)


# ─── Operations (Staff) ──────────────────────────────────────────────

@staff_required
def ops_dashboard(request):
    """Operations dashboard for staff users."""
    now = timezone.now()
    today = now.date()
    week_ago = today - timedelta(days=7)
    seven_days_out = today + timedelta(days=7)

    all_bookings = Booking.objects.all()

    # Action Required sections
    pending_confirmation = (
        all_bookings
        .filter(status='SUBMITTED')
        .select_related('customer', 'origin_port', 'destination_port', 'container_type')
        .order_by('submitted_at')
    )

    needs_carrier = (
        all_bookings
        .filter(status__in=['CONFIRMED', 'IN_TRANSIT'])
        .filter(Q(vessel_name='') | Q(etd__isnull=True) | Q(eta__isnull=True))
        .select_related('customer', 'origin_port', 'destination_port', 'container_type')
    )

    upcoming_departures = (
        all_bookings
        .filter(status__in=['CONFIRMED', 'IN_TRANSIT'])
        .filter(etd__gte=today, etd__lte=seven_days_out)
        .select_related('customer', 'origin_port', 'destination_port', 'container_type')
        .order_by('etd')
    )

    # Status pipeline counts
    pipeline = {
        'draft': all_bookings.filter(status='DRAFT').count(),
        'submitted': all_bookings.filter(status='SUBMITTED').count(),
        'confirmed': all_bookings.filter(status='CONFIRMED').count(),
        'in_transit': all_bookings.filter(status='IN_TRANSIT').count(),
        'completed': all_bookings.filter(status='COMPLETED').count(),
        'rejected': all_bookings.filter(status='REJECTED').count(),
        'cancelled': all_bookings.filter(status='CANCELLED').count(),
    }

    # Key stats
    submitted_today = all_bookings.filter(submitted_at__date=today).count()
    submitted_this_week = all_bookings.filter(submitted_at__date__gte=week_ago).count()

    # Average confirmation time (DB-level aggregation)
    avg_confirm_hours = None
    avg_result = all_bookings.filter(
        confirmed_at__isnull=False, submitted_at__isnull=False
    ).aggregate(avg_time=Avg(F('confirmed_at') - F('submitted_at')))
    if avg_result['avg_time'] is not None:
        avg_confirm_hours = avg_result['avg_time'].total_seconds() / 3600

    # Recent activity
    recent_activity = (
        AuditLog.objects
        .select_related('booking', 'performed_by')
        .order_by('-performed_at')[:20]
    )

    return render(request, 'bookings/ops/dashboard.html', {
        'pending_confirmation': pending_confirmation,
        'needs_carrier': needs_carrier,
        'upcoming_departures': upcoming_departures,
        'pipeline': pipeline,
        'submitted_today': submitted_today,
        'submitted_this_week': submitted_this_week,
        'avg_confirm_hours': avg_confirm_hours,
        'recent_activity': recent_activity,
    })


@staff_required
def ops_booking_confirm(request, booking_id):
    """Confirm a SUBMITTED booking with optional carrier details (staff only)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != 'SUBMITTED':
        messages.warning(request, f'This booking cannot be confirmed (current status: {booking.get_status_display()}).')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        carrier_form = CarrierDetailsForm(request.POST, instance=booking)
        try:
            BookingService.confirm_booking_with_carrier(
                booking, carrier_form, user=request.user, request=request)
            messages.success(request, f'Booking {booking.booking_number} confirmed successfully!')
            return redirect('booking_detail', booking_id=booking.id)
        except ValueError as e:
            messages.error(request, str(e))
    else:
        carrier_form = CarrierDetailsForm(instance=booking)

    return render(request, 'bookings/ops/booking_confirm.html', {
        'booking': booking,
        'carrier_form': carrier_form,
    })


@staff_required
def ops_booking_reject(request, booking_id):
    """Reject a SUBMITTED booking with reason (staff only)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != 'SUBMITTED':
        messages.warning(request, f'This booking cannot be rejected (current status: {booking.get_status_display()}).')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = RejectBookingForm(request.POST)
        if form.is_valid():
            try:
                BookingService.reject_booking(
                    booking, user=request.user,
                    reason=form.cleaned_data['reason'],
                    request=request)
                messages.success(request, f'Booking {booking.booking_number} has been rejected.')
                return redirect('booking_detail', booking_id=booking.id)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = RejectBookingForm()

    return render(request, 'bookings/ops/booking_reject.html', {
        'booking': booking,
        'form': form,
    })


@staff_required
def ops_carrier_details(request, booking_id):
    """Edit carrier details on a CONFIRMED or IN_TRANSIT booking (staff only)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status not in ('CONFIRMED', 'IN_TRANSIT'):
        messages.warning(request, 'Carrier details can only be edited on confirmed or in-transit bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = CarrierDetailsForm(request.POST, instance=booking)
        try:
            BookingService.update_carrier_details(
                booking, form, user=request.user, request=request)
            messages.success(request, 'Carrier details updated successfully.')
            return redirect('booking_detail', booking_id=booking.id)
        except ValueError as e:
            messages.error(request, str(e))
    else:
        form = CarrierDetailsForm(instance=booking)

    return render(request, 'bookings/ops/carrier_details.html', {
        'booking': booking,
        'form': form,
    })


@staff_required
def ops_mark_in_transit(request, booking_id):
    """Mark a CONFIRMED booking as in transit (staff only)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != 'CONFIRMED':
        messages.warning(request, 'Only confirmed bookings can be marked in transit.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = MarkInTransitForm(request.POST)
        if form.is_valid():
            try:
                BookingService.mark_in_transit(
                    booking, user=request.user, request=request,
                    actual_departure_date=form.cleaned_data.get('actual_departure_date'),
                )
                messages.success(request, f'Booking {booking.booking_number} marked as in transit.')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('booking_detail', booking_id=booking.id)
    else:
        form = MarkInTransitForm()

    return render(request, 'bookings/ops/mark_in_transit.html', {
        'booking': booking,
        'form': form,
    })


@staff_required
def ops_complete_booking(request, booking_id):
    """Mark an IN_TRANSIT booking as completed (staff only)."""
    booking = get_object_or_404(Booking, id=booking_id)

    if booking.status != 'IN_TRANSIT':
        messages.warning(request, 'Only in-transit bookings can be completed.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = CompleteBookingForm(request.POST)
        if form.is_valid():
            try:
                BookingService.complete_booking(
                    booking, user=request.user, request=request,
                    actual_arrival_date=form.cleaned_data.get('actual_arrival_date'),
                )
                messages.success(request, f'Booking {booking.booking_number} has been completed.')
            except ValueError as e:
                messages.error(request, str(e))
            return redirect('booking_detail', booking_id=booking.id)
    else:
        form = CompleteBookingForm()

    return render(request, 'bookings/ops/complete_booking.html', {
        'booking': booking,
        'form': form,
    })


# ─── Clone & Export ──────────────────────────────────────────────────

@login_required
def booking_clone(request, booking_id):
    """Clone a booking as a new DRAFT."""
    booking = get_booking_for_user(booking_id, request.user)
    customer = get_user_customer(request.user)

    if not customer:
        messages.error(request, 'Only customer users can clone bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        from django.db import transaction as db_transaction
        with db_transaction.atomic():
            new_booking = Booking(
                customer=customer,
                created_by=request.user,
                transport_mode=booking.transport_mode,
                origin_port=booking.origin_port,
                destination_port=booking.destination_port,
                cargo_ready_date=booking.cargo_ready_date,
                container_type=booking.container_type,
                container_count=booking.container_count,
                chargeable_weight_kg=booking.chargeable_weight_kg,
                flight_number=booking.flight_number,
                incoterms=booking.incoterms,
                incoterms_location=booking.incoterms_location,
                commodity_description=booking.commodity_description,
                is_hazardous=booking.is_hazardous,
                special_instructions=booking.special_instructions,
                status='DRAFT',
                source_channel='WEB',
            )
            new_booking.save()

            for item in booking.items.all():
                BookingItem.objects.create(
                    booking=new_booking,
                    description=item.description,
                    package_type=item.package_type,
                    quantity=item.quantity,
                    weight_kg=item.weight_kg,
                    hs_code=item.hs_code,
                    volume_cbm=item.volume_cbm,
                    length_cm=item.length_cm,
                    width_cm=item.width_cm,
                    height_cm=item.height_cm,
                    marks_and_numbers=item.marks_and_numbers,
                    is_hazardous=item.is_hazardous,
                    un_number=item.un_number,
                    imo_class=item.imo_class,
                    country_of_origin=item.country_of_origin,
                )

            for bp in booking.booking_parties.all():
                BookingParty.objects.create(
                    booking=new_booking,
                    party=bp.party,
                    role=bp.role,
                    company_name=bp.company_name,
                    contact_name=bp.contact_name,
                    address_text=bp.address_text,
                    email=bp.email,
                    phone=bp.phone,
                    tax_id=bp.tax_id,
                )

            new_booking.recalculate_totals()

            BookingService._log(
                new_booking, 'CREATED', user=request.user, request=request,
                notes=f'Cloned from {booking.booking_number}',
                new_value=BookingService._booking_snapshot(new_booking),
            )

        messages.success(request, f'Booking cloned as {new_booking.booking_number} (DRAFT).')
        return redirect('booking_detail', booking_id=new_booking.id)

    return redirect('booking_detail', booking_id=booking.id)


@login_required
def booking_export_csv(request):
    """Export filtered bookings as CSV."""
    customer = get_user_customer(request.user)
    if customer:
        bookings = Booking.objects.filter(customer=customer)
    else:
        bookings = Booking.objects.all()

    bookings = bookings.select_related(
        'customer', 'origin_port', 'destination_port', 'container_type'
    )

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
            Q(destination_port__name__icontains=search_query) |
            Q(external_reference__icontains=search_query)
        )

    bookings = bookings.order_by('-created_at')

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="bookings_export.csv"'

    is_staff = not customer

    writer = csv.writer(response)
    headers = [
        'Booking Number', 'Status', 'Transport Mode', 'Customer',
        'Origin', 'Destination',
        'Container Type', 'Container Count',
        'Chargeable Weight (kg)', 'Flight Number',
        'Cargo Ready Date', 'Cargo Cutoff',
        'INCOTERMS', 'Carrier', 'Vessel', 'Voyage Number', 'ETD', 'ETA',
    ]
    if is_staff:
        headers.append('Contract Number')
    headers += [
        'Actual Departure', 'Actual Arrival',
        'Total Weight (kg)', 'Total Volume (CBM)',
        'Created', 'Submitted', 'Confirmed', 'In Transit', 'Completed',
    ]
    writer.writerow(headers)

    for b in bookings:
        row = [
            b.booking_number, b.status, b.get_transport_mode_display(),
            b.customer.code,
            b.origin_port.code, b.destination_port.code,
            b.container_type.code if b.container_type else '', b.container_count or '',
            b.chargeable_weight_kg or '', b.flight_number or '',
            b.cargo_ready_date, b.cargo_cutoff_date or '',
            b.incoterms, b.carrier_name, b.vessel_name, b.voyage_number or '',
            b.etd or '', b.eta or '',
        ]
        if is_staff:
            row.append(b.contract_number)
        row += [
            b.actual_departure_date or '', b.actual_arrival_date or '',
            b.total_weight_kg or '', b.total_volume_cbm or '',
            b.created_at.strftime('%Y-%m-%d %H:%M'),
            b.submitted_at.strftime('%Y-%m-%d %H:%M') if b.submitted_at else '',
            b.confirmed_at.strftime('%Y-%m-%d %H:%M') if b.confirmed_at else '',
            b.in_transit_at.strftime('%Y-%m-%d %H:%M') if b.in_transit_at else '',
            b.completed_at.strftime('%Y-%m-%d %H:%M') if b.completed_at else '',
        ]
        writer.writerow(row)

    return response
