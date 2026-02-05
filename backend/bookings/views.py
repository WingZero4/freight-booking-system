from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Booking, BookingItem, Port, ContainerType


@login_required
def booking_list(request):
    """List bookings for current user's customer"""
    if hasattr(request.user, 'profile') and request.user.profile.customer:
        bookings = Booking.objects.filter(customer=request.user.profile.customer)
    else:
        # Staff sees all bookings
        bookings = Booking.objects.all()

    return render(request, 'bookings/booking_list.html', {'bookings': bookings})


@login_required
def booking_create(request):
    """Create a new booking"""
    if request.method == 'POST':
        # Get customer from user profile
        if not hasattr(request.user, 'profile') or not request.user.profile.customer:
            messages.error(request, 'You must be associated with a customer to create bookings.')
            return redirect('booking_list')

        customer = request.user.profile.customer

        # Get form data
        origin_port = get_object_or_404(Port, id=request.POST.get('origin_port'))
        destination_port = get_object_or_404(Port, id=request.POST.get('destination_port'))
        container_type = get_object_or_404(ContainerType, id=request.POST.get('container_type'))

        # Create booking
        booking = Booking.objects.create(
            customer=customer,
            created_by=request.user,
            origin_port=origin_port,
            destination_port=destination_port,
            cargo_ready_date=request.POST.get('cargo_ready_date'),
            container_type=container_type,
            container_count=int(request.POST.get('container_count', 1)),
            special_instructions=request.POST.get('special_instructions', ''),
        )

        # Create cargo item
        BookingItem.objects.create(
            booking=booking,
            description=request.POST.get('cargo_description'),
            package_type='PACKAGE',
            quantity=int(request.POST.get('cargo_quantity', 1)),
            weight_kg=float(request.POST.get('cargo_weight', 0)),
        )

        messages.success(request, f'Booking {booking.booking_number} created successfully!')
        return redirect('booking_detail', booking_id=booking.id)

    # GET request - show form
    ports = Port.objects.filter(is_active=True)
    container_types = ContainerType.objects.all()

    return render(request, 'bookings/booking_form.html', {
        'ports': ports,
        'container_types': container_types,
    })


@login_required
def booking_detail(request, booking_id):
    """View booking details"""
    booking = get_object_or_404(Booking, id=booking_id)

    # Check permission
    if hasattr(request.user, 'profile') and request.user.profile.customer:
        if booking.customer != request.user.profile.customer:
            messages.error(request, 'You do not have permission to view this booking.')
            return redirect('booking_list')

    return render(request, 'bookings/booking_detail.html', {'booking': booking})


@login_required
def booking_submit(request, booking_id):
    """Submit a draft booking"""
    booking = get_object_or_404(Booking, id=booking_id)

    # Check permission
    if hasattr(request.user, 'profile') and request.user.profile.customer:
        if booking.customer != request.user.profile.customer:
            messages.error(request, 'You do not have permission to submit this booking.')
            return redirect('booking_list')

    if booking.status == 'DRAFT':
        booking.submit()
        messages.success(request, f'Booking {booking.booking_number} submitted successfully!')
    else:
        messages.warning(request, 'This booking has already been submitted.')

    return redirect('booking_detail', booking_id=booking.id)
