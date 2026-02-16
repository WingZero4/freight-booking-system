from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from .models import Booking
from .pdf_utils import build_booking_pdf
from .views import get_user_customer, staff_required


@login_required
def booking_confirmation_pdf(request, booking_id):
    """Generate a booking confirmation PDF (accessible to booking owner or staff)."""
    customer = get_user_customer(request.user)
    if customer:
        booking = get_object_or_404(
            Booking.objects.select_related(
                'customer', 'origin_port', 'destination_port', 'container_type',
            ).prefetch_related('items', 'booking_parties'),
            pk=booking_id, customer=customer,
        )
    else:
        booking = get_object_or_404(
            Booking.objects.select_related(
                'customer', 'origin_port', 'destination_port', 'container_type',
            ).prefetch_related('items', 'booking_parties'),
            pk=booking_id,
        )

    buffer = build_booking_pdf(booking, include_internal=False)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="booking_confirmation_{booking.booking_number}.pdf"'
    )
    return response


@staff_required
def shipping_advice_pdf(request, booking_id):
    """Generate a shipping advice PDF (staff only, confirmed/in-transit bookings)."""
    booking = get_object_or_404(
        Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port', 'container_type',
        ).prefetch_related('items', 'booking_parties'),
        pk=booking_id,
        status__in=['CONFIRMED', 'IN_TRANSIT', 'ARRIVED', 'COMPLETED'],
    )

    buffer = build_booking_pdf(booking, include_internal=True)

    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="shipping_advice_{booking.booking_number}.pdf"'
    )
    return response
