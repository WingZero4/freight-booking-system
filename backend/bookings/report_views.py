import csv
from datetime import timedelta, date as date_type

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Sum, F, Q
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import Booking
from .views import staff_required, get_user_customer


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_date_range(request):
    """Parse date range from GET params. Returns (start_date, end_date)."""
    today = timezone.now().date()
    preset = request.GET.get('preset', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if preset == '7d':
        start_date = today - timedelta(days=7)
        end_date = today
    elif preset == '90d':
        start_date = today - timedelta(days=90)
        end_date = today
    elif preset == 'ytd':
        start_date = today.replace(month=1, day=1)
        end_date = today
    elif date_from and date_to:
        try:
            start_date = date_type.fromisoformat(date_from)
            end_date = date_type.fromisoformat(date_to)
        except ValueError:
            start_date = today - timedelta(days=30)
            end_date = today
    else:
        start_date = today - timedelta(days=30)
        end_date = today

    return start_date, end_date


def _base_bookings(request, start_date, end_date):
    """Return (queryset, customer_or_none) filtered by user permissions and date range."""
    customer = get_user_customer(request.user)
    bookings = Booking.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )
    if customer:
        bookings = bookings.filter(customer=customer)
    return bookings, customer


def _csv_response(filename):
    """Create an HttpResponse with CSV content type and attachment header."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')  # UTF-8 BOM for Excel compatibility
    return response


# ---------------------------------------------------------------------------
# Staff reports hub
# ---------------------------------------------------------------------------

@staff_required
def ops_reports_hub(request):
    """Staff reports landing page with links to all reports."""
    return render(request, 'bookings/ops/reports_hub.html')


# ---------------------------------------------------------------------------
# Staff: Overview (existing report, refactored)
# ---------------------------------------------------------------------------

@staff_required
def ops_reports(request):
    """Staff analytics overview with date-range filtering."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    total = bookings.count()
    by_status = bookings.values('status').annotate(count=Count('id')).order_by('status')
    status_counts = {s['status']: s['count'] for s in by_status}

    avg_confirm = bookings.filter(
        confirmed_at__isnull=False, submitted_at__isnull=False
    ).aggregate(avg_hours=Avg(F('confirmed_at') - F('submitted_at')))
    avg_confirm_hours = None
    if avg_confirm['avg_hours']:
        avg_confirm_hours = round(avg_confirm['avg_hours'].total_seconds() / 3600, 1)

    by_transport = list(bookings.values('transport_mode').annotate(count=Count('id')).order_by('-count'))
    transport_labels = dict(Booking.TRANSPORT_MODE_CHOICES)
    for item in by_transport:
        item['display'] = transport_labels.get(item['transport_mode'], item['transport_mode'])

    by_customer = bookings.values('customer__name', 'customer__code').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    by_channel = list(bookings.values('source_channel').annotate(count=Count('id')).order_by('-count'))
    channel_labels = dict(Booking.SOURCE_CHANNEL_CHOICES)
    for item in by_channel:
        item['display'] = channel_labels.get(item['source_channel'], item['source_channel'])

    context = {
        'start_date': start_date,
        'end_date': end_date,
        'total': total,
        'status_counts': status_counts,
        'avg_confirm_hours': avg_confirm_hours,
        'by_transport': by_transport,
        'by_customer': by_customer,
        'by_channel': by_channel,
    }
    return render(request, 'bookings/ops/reports.html', context)


# ---------------------------------------------------------------------------
# Staff: Volume by Customer
# ---------------------------------------------------------------------------

@staff_required
def ops_report_volume_by_customer(request):
    """Bookings per customer with weight, volume, and container totals."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    data = (
        bookings
        .values('customer__code', 'customer__name')
        .annotate(
            booking_count=Count('id'),
            total_weight=Sum('total_weight_kg'),
            total_volume=Sum('total_volume_cbm'),
            total_containers=Sum('container_count'),
        )
        .order_by('-booking_count')
    )

    totals = bookings.aggregate(
        total_bookings=Count('id'),
        grand_weight=Sum('total_weight_kg'),
        grand_volume=Sum('total_volume_cbm'),
        grand_containers=Sum('container_count'),
    )

    if request.GET.get('format') == 'csv':
        response = _csv_response('volume_by_customer.csv')
        writer = csv.writer(response)
        writer.writerow(['Customer Code', 'Customer Name', 'Bookings', 'Weight (kg)', 'Volume (CBM)', 'Containers'])
        for row in data:
            writer.writerow([
                row['customer__code'], row['customer__name'],
                row['booking_count'],
                row['total_weight'] or 0, row['total_volume'] or 0,
                row['total_containers'] or 0,
            ])
        return response

    return render(request, 'bookings/ops/report_volume_customer.html', {
        'start_date': start_date, 'end_date': end_date,
        'data': data, 'totals': totals,
        'report_title': 'Volume by Customer',
    })


# ---------------------------------------------------------------------------
# Staff: Route Analysis
# ---------------------------------------------------------------------------

@staff_required
def ops_report_route_analysis(request):
    """Top origin-destination pairs with volume and weight."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    data = (
        bookings
        .values(
            'origin_port__code', 'origin_port__name',
            'destination_port__code', 'destination_port__name',
        )
        .annotate(
            booking_count=Count('id'),
            total_weight=Sum('total_weight_kg'),
            total_volume=Sum('total_volume_cbm'),
        )
        .order_by('-booking_count')[:30]
    )

    if request.GET.get('format') == 'csv':
        response = _csv_response('route_analysis.csv')
        writer = csv.writer(response)
        writer.writerow(['Origin Code', 'Origin Name', 'Dest Code', 'Dest Name', 'Bookings', 'Weight (kg)', 'Volume (CBM)'])
        for row in data:
            writer.writerow([
                row['origin_port__code'], row['origin_port__name'],
                row['destination_port__code'], row['destination_port__name'],
                row['booking_count'],
                row['total_weight'] or 0, row['total_volume'] or 0,
            ])
        return response

    return render(request, 'bookings/ops/report_route_analysis.html', {
        'start_date': start_date, 'end_date': end_date,
        'data': data,
        'report_title': 'Route Analysis',
    })


# ---------------------------------------------------------------------------
# Staff: Transit Performance
# ---------------------------------------------------------------------------

@staff_required
def ops_report_transit_performance(request):
    """Average transit times and on-time delivery rates."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    completed = bookings.filter(
        status='COMPLETED',
        etd__isnull=False,
        actual_arrival_date__isnull=False,
    ).select_related('origin_port', 'destination_port')

    transit_data = []
    total_days = 0
    on_time_count = 0
    late_count = 0

    for b in completed.order_by('-actual_arrival_date')[:50]:
        days = (b.actual_arrival_date - b.etd).days
        is_on_time = b.eta and b.actual_arrival_date <= b.eta
        days_late = None
        if b.eta and not is_on_time:
            days_late = (b.actual_arrival_date - b.eta).days
        transit_data.append({
            'booking_number': b.booking_number,
            'origin': b.origin_port.code,
            'destination': b.destination_port.code,
            'carrier': b.carrier_name,
            'etd': b.etd,
            'eta': b.eta,
            'actual_arrival': b.actual_arrival_date,
            'transit_days': days,
            'on_time': is_on_time,
            'days_late': days_late,
        })
        total_days += days
        if is_on_time:
            on_time_count += 1
        elif b.eta:
            late_count += 1

    count = len(transit_data)
    avg_transit_days = round(total_days / count, 1) if count else None
    rated = on_time_count + late_count
    on_time_pct = round(on_time_count / rated * 100, 1) if rated else None

    if request.GET.get('format') == 'csv':
        response = _csv_response('transit_performance.csv')
        writer = csv.writer(response)
        writer.writerow(['Booking', 'Origin', 'Dest', 'Carrier', 'ETD', 'ETA', 'Actual Arrival', 'Transit Days', 'On Time'])
        for row in transit_data:
            writer.writerow([
                row['booking_number'], row['origin'], row['destination'],
                row['carrier'], row['etd'], row['eta'], row['actual_arrival'],
                row['transit_days'],
                'Yes' if row['on_time'] else ('No' if row['on_time'] is False else ''),
            ])
        return response

    return render(request, 'bookings/ops/report_transit_performance.html', {
        'start_date': start_date, 'end_date': end_date,
        'transit_data': transit_data,
        'avg_transit_days': avg_transit_days,
        'on_time_pct': on_time_pct,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'total_count': count,
        'report_title': 'Transit Performance',
    })


# ---------------------------------------------------------------------------
# Staff: Container Utilization
# ---------------------------------------------------------------------------

@staff_required
def ops_report_container_utilization(request):
    """Breakdown by container type for FCL bookings."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    fcl_bookings = bookings.filter(
        transport_mode='SEA_FCL',
        container_type__isnull=False,
    )

    data = (
        fcl_bookings
        .values('container_type__code', 'container_type__name', 'container_type__size_ft')
        .annotate(
            booking_count=Count('id'),
            total_containers=Sum('container_count'),
            avg_per_booking=Avg('container_count'),
        )
        .order_by('-total_containers')
    )

    totals = fcl_bookings.aggregate(
        total_bookings=Count('id'),
        grand_containers=Sum('container_count'),
    )

    if request.GET.get('format') == 'csv':
        response = _csv_response('container_utilization.csv')
        writer = csv.writer(response)
        writer.writerow(['Container Type', 'Name', 'Size (ft)', 'Bookings', 'Total Containers', 'Avg per Booking'])
        for row in data:
            writer.writerow([
                row['container_type__code'], row['container_type__name'],
                row['container_type__size_ft'], row['booking_count'],
                row['total_containers'] or 0,
                round(row['avg_per_booking'], 1) if row['avg_per_booking'] is not None else 0,
            ])
        return response

    return render(request, 'bookings/ops/report_container_util.html', {
        'start_date': start_date, 'end_date': end_date,
        'data': data, 'totals': totals,
        'report_title': 'Container Utilization',
    })


# ---------------------------------------------------------------------------
# Staff: Carrier Performance
# ---------------------------------------------------------------------------

@staff_required
def ops_report_carrier_performance(request):
    """Bookings by carrier with transit time averages."""
    start_date, end_date = _parse_date_range(request)
    bookings, _ = _base_bookings(request, start_date, end_date)

    carrier_bookings = bookings.exclude(carrier_name='')

    data = list(
        carrier_bookings
        .values('carrier_name')
        .annotate(
            booking_count=Count('id'),
            completed_count=Count('id', filter=Q(status='COMPLETED')),
            total_weight=Sum('total_weight_kg'),
        )
        .order_by('-booking_count')
    )

    for row in data:
        completed = carrier_bookings.filter(
            carrier_name=row['carrier_name'],
            status='COMPLETED',
            etd__isnull=False,
            actual_arrival_date__isnull=False,
        )
        transit_days_list = [
            (b['actual_arrival_date'] - b['etd']).days
            for b in completed.values('etd', 'actual_arrival_date')
        ]
        row['avg_transit_days'] = round(sum(transit_days_list) / len(transit_days_list), 1) if transit_days_list else None

    if request.GET.get('format') == 'csv':
        response = _csv_response('carrier_performance.csv')
        writer = csv.writer(response)
        writer.writerow(['Carrier', 'Total Bookings', 'Completed', 'Weight (kg)', 'Avg Transit Days'])
        for row in data:
            writer.writerow([
                row['carrier_name'], row['booking_count'],
                row['completed_count'], row['total_weight'] or 0,
                row['avg_transit_days'] if row['avg_transit_days'] is not None else '',
            ])
        return response

    return render(request, 'bookings/ops/report_carrier_performance.html', {
        'start_date': start_date, 'end_date': end_date,
        'data': data,
        'report_title': 'Carrier Performance',
    })


# ---------------------------------------------------------------------------
# Staff: Status Aging (point-in-time, no date range)
# ---------------------------------------------------------------------------

@staff_required
def ops_report_status_aging(request):
    """How long bookings currently sit in each active status."""
    now = timezone.now()
    active_statuses = ['SUBMITTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED']
    ts_field_map = {
        'SUBMITTED': 'submitted_at',
        'CONFIRMED': 'confirmed_at',
        'PACKING': 'packing_at',
        'IN_TRANSIT': 'in_transit_at',
        'ARRIVED': 'arrived_at',
    }
    status_labels = dict(Booking.STATUS_CHOICES)

    aging_data = []
    for status in active_statuses:
        qs = Booking.objects.filter(status=status).select_related(
            'customer', 'origin_port', 'destination_port'
        )
        ts_field = ts_field_map[status]

        entries = []
        total_age = 0
        counted = 0
        for b in qs:
            entered_at = getattr(b, ts_field)
            if entered_at:
                age_days = round((now - entered_at).total_seconds() / 86400, 1)
                total_age += age_days
                counted += 1
            else:
                age_days = None
            entries.append({'booking': b, 'age_days': age_days})
        entries.sort(key=lambda x: x['age_days'] or 0, reverse=True)

        aging_data.append({
            'status': status,
            'status_display': status_labels.get(status, status),
            'count': len(entries),
            'all_entries': entries,
            'entries': entries[:20],
            'avg_age_days': round(total_age / counted, 1) if counted else None,
        })

    if request.GET.get('format') == 'csv':
        response = _csv_response('status_aging.csv')
        writer = csv.writer(response)
        writer.writerow(['Booking', 'Status', 'Customer', 'Route', 'Age (Days)'])
        for group in aging_data:
            for entry in group['all_entries']:
                b = entry['booking']
                writer.writerow([
                    b.booking_number, group['status_display'],
                    b.customer.code,
                    f"{b.origin_port.code} > {b.destination_port.code}",
                    entry['age_days'],
                ])
        return response

    return render(request, 'bookings/ops/report_status_aging.html', {
        'aging_data': aging_data,
        'report_title': 'Status Aging',
    })


# ---------------------------------------------------------------------------
# Customer reports hub
# ---------------------------------------------------------------------------

@login_required
def customer_reports_hub(request):
    """Customer reports landing page."""
    customer = get_user_customer(request.user)
    if not customer:
        return redirect('ops_reports_hub')
    return render(request, 'bookings/reports_hub.html')


# ---------------------------------------------------------------------------
# Customer: Booking Summary
# ---------------------------------------------------------------------------

@login_required
def customer_report_summary(request):
    """Customer booking summary — status dist, monthly trend, transport mode."""
    customer = get_user_customer(request.user)
    if not customer:
        return redirect('ops_reports_hub')

    start_date, end_date = _parse_date_range(request)
    bookings = Booking.objects.filter(
        customer=customer,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )

    total = bookings.count()
    by_status = bookings.values('status').annotate(count=Count('id')).order_by('status')
    status_counts = {s['status']: s['count'] for s in by_status}

    by_transport = list(bookings.values('transport_mode').annotate(count=Count('id')).order_by('-count'))
    transport_labels = dict(Booking.TRANSPORT_MODE_CHOICES)
    for item in by_transport:
        item['display'] = transport_labels.get(item['transport_mode'], item['transport_mode'])

    monthly_trend = (
        bookings
        .annotate(month=TruncMonth('created_at'))
        .values('month')
        .annotate(created=Count('id'), completed=Count('id', filter=Q(status='COMPLETED')))
        .order_by('month')
    )

    weight_volume = bookings.aggregate(
        total_weight=Sum('total_weight_kg'),
        total_volume=Sum('total_volume_cbm'),
    )

    if request.GET.get('format') == 'csv':
        response = _csv_response('my_booking_summary.csv')
        writer = csv.writer(response)
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Bookings', total])
        for status, count in status_counts.items():
            writer.writerow([f'Status: {status}', count])
        for item in by_transport:
            writer.writerow([f'Transport: {item["display"]}', item['count']])
        writer.writerow(['Total Weight (kg)', weight_volume['total_weight'] or 0])
        writer.writerow(['Total Volume (CBM)', weight_volume['total_volume'] or 0])
        return response

    return render(request, 'bookings/report_summary.html', {
        'start_date': start_date, 'end_date': end_date,
        'total': total,
        'status_counts': status_counts,
        'by_transport': by_transport,
        'monthly_trend': monthly_trend,
        'weight_volume': weight_volume,
        'report_title': 'My Booking Summary',
    })


# ---------------------------------------------------------------------------
# Customer: Route History
# ---------------------------------------------------------------------------

@login_required
def customer_report_routes(request):
    """Customer's most-used routes."""
    customer = get_user_customer(request.user)
    if not customer:
        return redirect('ops_reports_hub')

    start_date, end_date = _parse_date_range(request)
    bookings = Booking.objects.filter(
        customer=customer,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )

    data = (
        bookings
        .values(
            'origin_port__code', 'origin_port__name',
            'destination_port__code', 'destination_port__name',
        )
        .annotate(
            booking_count=Count('id'),
            total_weight=Sum('total_weight_kg'),
            total_volume=Sum('total_volume_cbm'),
        )
        .order_by('-booking_count')[:20]
    )

    if request.GET.get('format') == 'csv':
        response = _csv_response('my_route_history.csv')
        writer = csv.writer(response)
        writer.writerow(['Origin Code', 'Origin Name', 'Dest Code', 'Dest Name', 'Bookings', 'Weight (kg)', 'Volume (CBM)'])
        for row in data:
            writer.writerow([
                row['origin_port__code'], row['origin_port__name'],
                row['destination_port__code'], row['destination_port__name'],
                row['booking_count'], row['total_weight'] or 0, row['total_volume'] or 0,
            ])
        return response

    return render(request, 'bookings/report_routes.html', {
        'start_date': start_date, 'end_date': end_date,
        'data': data,
        'report_title': 'My Route History',
    })


# ---------------------------------------------------------------------------
# Customer: Shipment Performance
# ---------------------------------------------------------------------------

@login_required
def customer_report_performance(request):
    """Transit times and on-time rates for customer's completed bookings."""
    customer = get_user_customer(request.user)
    if not customer:
        return redirect('ops_reports_hub')

    start_date, end_date = _parse_date_range(request)
    completed = Booking.objects.filter(
        customer=customer,
        status='COMPLETED',
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        etd__isnull=False,
        actual_arrival_date__isnull=False,
    ).select_related('origin_port', 'destination_port')

    transit_data = []
    total_days = 0
    on_time_count = 0
    late_count = 0

    for b in completed.order_by('-actual_arrival_date')[:50]:
        days = (b.actual_arrival_date - b.etd).days
        is_on_time = b.eta and b.actual_arrival_date <= b.eta
        transit_data.append({
            'booking_number': b.booking_number,
            'origin': b.origin_port.code,
            'destination': b.destination_port.code,
            'carrier': b.carrier_name,
            'etd': b.etd,
            'eta': b.eta,
            'actual_arrival': b.actual_arrival_date,
            'transit_days': days,
            'on_time': is_on_time,
        })
        total_days += days
        if is_on_time:
            on_time_count += 1
        elif b.eta:
            late_count += 1

    count = len(transit_data)
    avg_transit_days = round(total_days / count, 1) if count else None
    rated = on_time_count + late_count
    on_time_pct = round(on_time_count / rated * 100, 1) if rated else None

    if request.GET.get('format') == 'csv':
        response = _csv_response('my_shipment_performance.csv')
        writer = csv.writer(response)
        writer.writerow(['Booking', 'Origin', 'Dest', 'Carrier', 'ETD', 'ETA', 'Actual Arrival', 'Transit Days', 'On Time'])
        for row in transit_data:
            writer.writerow([
                row['booking_number'], row['origin'], row['destination'],
                row['carrier'], row['etd'], row['eta'], row['actual_arrival'],
                row['transit_days'],
                'Yes' if row['on_time'] else ('No' if row['on_time'] is False else ''),
            ])
        return response

    return render(request, 'bookings/report_performance.html', {
        'start_date': start_date, 'end_date': end_date,
        'transit_data': transit_data,
        'avg_transit_days': avg_transit_days,
        'on_time_pct': on_time_pct,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'total_count': count,
        'report_title': 'My Shipment Performance',
    })
