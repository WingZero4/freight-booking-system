from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from .models import Booking, BookingDocument, Party, BookingParty
from .forms import (
    BookingForm, BookingItemFormSet, BookingDocumentForm,
    PartyForm, BookingPartySelectForm,
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
    booking = get_object_or_404(Booking, id=booking_id)
    customer = get_user_customer(user)
    if customer and booking.customer != customer:
        raise Http404
    return booking


# ─── Dashboard ────────────────────────────────────────────────────────

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
    if customer and booking.status in ('DRAFT', 'SUBMITTED'):
        party_select_form = BookingPartySelectForm(customer)

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
    """Cancel a booking (DRAFT or SUBMITTED only, POST required)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status not in ['DRAFT', 'SUBMITTED']:
        messages.error(request, 'This booking cannot be cancelled.')
        return redirect('booking_detail', booking_id=booking.id)

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


# ─── Documents ────────────────────────────────────────────────────────

@login_required
def booking_document_upload(request, booking_id):
    """Upload a document to a booking (DRAFT or SUBMITTED only)"""
    booking = get_booking_for_user(booking_id, request.user)

    if booking.status not in ['DRAFT', 'SUBMITTED']:
        messages.error(request, 'Documents can only be uploaded to draft or submitted bookings.')
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

    if not customer:
        messages.error(request, 'You must be associated with a customer to manage parties.')
        return redirect('booking_detail', booking_id=booking.id)

    if booking.status not in ('DRAFT', 'SUBMITTED'):
        messages.error(request, 'Parties can only be added to draft or submitted bookings.')
        return redirect('booking_detail', booking_id=booking.id)

    if request.method == 'POST':
        form = BookingPartySelectForm(customer, request.POST)
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

    if booking.status not in ('DRAFT', 'SUBMITTED'):
        messages.error(request, 'Parties can only be removed from draft or submitted bookings.')
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
