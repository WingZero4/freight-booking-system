"""Advanced filters for booking API using django-filter."""
import django_filters
from django.db import models

from .models import Booking


class BookingFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(choices=Booking.STATUS_CHOICES)
    transport_mode = django_filters.ChoiceFilter(
        choices=Booking.TRANSPORT_MODE_CHOICES,
    )
    customer_code = django_filters.CharFilter(field_name='customer__code')
    origin = django_filters.CharFilter(field_name='origin_port__code')
    destination = django_filters.CharFilter(
        field_name='destination_port__code',
    )
    created_after = django_filters.DateFilter(
        field_name='created_at', lookup_expr='date__gte',
    )
    created_before = django_filters.DateFilter(
        field_name='created_at', lookup_expr='date__lte',
    )
    cargo_ready_after = django_filters.DateFilter(
        field_name='cargo_ready_date', lookup_expr='gte',
    )
    cargo_ready_before = django_filters.DateFilter(
        field_name='cargo_ready_date', lookup_expr='lte',
    )
    source_channel = django_filters.ChoiceFilter(
        choices=Booking.SOURCE_CHANNEL_CHOICES,
    )
    booking_number = django_filters.CharFilter(lookup_expr='icontains')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Booking
        fields = []

    def filter_search(self, queryset, name, value):
        """Search across booking number, customer name, external ref."""
        return queryset.filter(
            models.Q(booking_number__icontains=value)
            | models.Q(customer__name__icontains=value)
            | models.Q(external_reference__icontains=value)
        )
