"""Auto-quoting service — match booking parameters to rate sheets."""

from datetime import date

from django.db import models as db_models


def get_available_rates(origin_port_id, destination_port_id, transport_mode=None,
                        container_type_id=None):
    """Get valid rate sheets matching the given parameters.

    Returns queryset of RateSheet objects sorted by rate_amount ascending.
    """
    from .models import RateSheet

    today = date.today()
    qs = RateSheet.objects.filter(
        origin_port_id=origin_port_id,
        destination_port_id=destination_port_id,
        is_active=True,
        valid_from__lte=today,
        valid_to__gte=today,
    ).select_related('carrier', 'origin_port', 'destination_port', 'container_type')

    # Map booking transport_mode to rate transport_mode
    if transport_mode:
        mode_map = {
            'SEA_FCL': 'SEA', 'SEA_LCL': 'SEA',
            'AIR': 'AIR', 'RAIL': 'RAIL',
            'TRUCK': 'ROAD', 'SEA_AIR': 'SEA',
            'AIR_SEA': 'AIR', 'MULTIMODAL': None,
        }
        rate_mode = mode_map.get(transport_mode)
        if rate_mode:
            qs = qs.filter(transport_mode=rate_mode)

    if container_type_id:
        qs = qs.filter(
            db_models.Q(container_type_id=container_type_id) |
            db_models.Q(container_type__isnull=True)
        )

    return qs.order_by('rate_amount')


def get_best_rate(origin_port_id, destination_port_id, transport_mode=None,
                  container_type_id=None):
    """Get the cheapest valid rate for the given parameters."""
    rates = get_available_rates(
        origin_port_id, destination_port_id, transport_mode, container_type_id)
    return rates.first()


def format_rate_comparison(rates):
    """Format rates for display in booking form.

    Returns list of dicts for JSON response.
    """
    result = []
    for rate in rates[:10]:  # Max 10 options
        result.append({
            'id': rate.id,
            'carrier': rate.carrier.name,
            'carrier_code': rate.carrier.scac_code,
            'rate_amount': str(rate.rate_amount),
            'currency': rate.currency,
            'rate_basis': rate.get_rate_basis_display(),
            'transit_days': rate.transit_days,
            'valid_until': str(rate.valid_to),
            'container_type': rate.container_type.code if rate.container_type else None,
            'notes': rate.notes,
        })
    return result


def get_rates_for_booking_form(origin_port_id, destination_port_id,
                                transport_mode=None, container_type_id=None):
    """Entry point for AJAX rate lookup from booking form."""
    rates = get_available_rates(
        origin_port_id, destination_port_id, transport_mode, container_type_id)
    return format_rate_comparison(rates)
