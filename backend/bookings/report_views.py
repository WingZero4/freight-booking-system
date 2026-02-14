from datetime import timedelta

from django.shortcuts import render
from django.db.models import Count, Avg, F, Q
from django.utils import timezone

from .models import Booking
from .views import staff_required


@staff_required
def ops_reports(request):
    """Staff analytics page with date-range filtering."""
    # Date range
    today = timezone.now().date()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    preset = request.GET.get('preset', '')

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
            from datetime import date as date_type
            start_date = date_type.fromisoformat(date_from)
            end_date = date_type.fromisoformat(date_to)
        except ValueError:
            start_date = today - timedelta(days=30)
            end_date = today
    else:
        # Default: last 30 days
        start_date = today - timedelta(days=30)
        end_date = today

    # Base queryset filtered by date range
    bookings = Booking.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )

    # Summary stats
    total = bookings.count()
    by_status = bookings.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    status_counts = {s['status']: s['count'] for s in by_status}

    # Average confirmation time (submitted_at → confirmed_at)
    avg_confirm = bookings.filter(
        confirmed_at__isnull=False, submitted_at__isnull=False
    ).aggregate(
        avg_hours=Avg(F('confirmed_at') - F('submitted_at'))
    )
    avg_confirm_hours = None
    if avg_confirm['avg_hours']:
        avg_confirm_hours = round(avg_confirm['avg_hours'].total_seconds() / 3600, 1)

    # By transport mode
    by_transport = bookings.values('transport_mode').annotate(
        count=Count('id')
    ).order_by('-count')

    # Top 10 customers
    by_customer = bookings.values(
        'customer__name', 'customer__code'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    # By source channel
    by_channel = bookings.values('source_channel').annotate(
        count=Count('id')
    ).order_by('-count')

    # Transport mode display names
    transport_labels = dict(Booking.TRANSPORT_MODE_CHOICES)
    for item in by_transport:
        item['display'] = transport_labels.get(item['transport_mode'], item['transport_mode'])

    # Channel display names
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
