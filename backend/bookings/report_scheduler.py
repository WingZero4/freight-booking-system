"""Scheduled report generation and email service."""

import io
from datetime import date, timedelta

from django.core.mail import EmailMessage
from django.db.models import Count, Q, Avg, F
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


def _get_date_range(report):
    """Calculate date range based on report frequency."""
    today = date.today()
    if report.frequency == 'DAILY':
        return today - timedelta(days=1), today
    elif report.frequency == 'WEEKLY':
        return today - timedelta(days=7), today
    elif report.frequency == 'MONTHLY':
        return today.replace(day=1) - timedelta(days=1), today
    return today - timedelta(days=7), today


def _is_report_due(report):
    """Check if a scheduled report is due to be sent now."""
    now = timezone.now()
    current_hour = now.hour

    # Check hour
    if current_hour != report.hour:
        return False

    # Check if already sent this period
    if report.last_sent_at:
        if report.frequency == 'DAILY' and report.last_sent_at.date() == now.date():
            return False
        elif report.frequency == 'WEEKLY':
            if (now - report.last_sent_at).days < 6:
                return False
        elif report.frequency == 'MONTHLY':
            if report.last_sent_at.month == now.month and report.last_sent_at.year == now.year:
                return False

    # Check day constraints
    if report.frequency == 'WEEKLY' and report.day_of_week is not None:
        if now.weekday() != report.day_of_week:
            return False
    elif report.frequency == 'MONTHLY' and report.day_of_month is not None:
        if now.day != report.day_of_month:
            return False

    return True


def generate_report_pdf(organization, report_type, start_date, end_date):
    """Generate a PDF report and return as BytesIO."""
    from .models import Booking

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph(
        f'{organization.name} — {report_type.replace("_", " ").title()}',
        styles['Title']))
    elements.append(Paragraph(
        f'Period: {start_date} to {end_date}', styles['Normal']))
    elements.append(Spacer(1, 0.3 * inch))

    bookings = Booking.objects.filter(
        customer__organization=organization,
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    )

    if report_type in ('WEEKLY_SUMMARY', 'MONTHLY_SUMMARY'):
        _add_summary_section(elements, styles, bookings)
    elif report_type == 'CARRIER_PERFORMANCE':
        _add_carrier_section(elements, styles, bookings)
    elif report_type == 'VOLUME_BY_CUSTOMER':
        _add_volume_section(elements, styles, bookings)

    doc.build(elements)
    buf.seek(0)
    return buf


def _add_summary_section(elements, styles, bookings):
    """Add summary statistics to report."""
    stats = bookings.aggregate(
        total=Count('id'),
        draft=Count('id', filter=Q(status='DRAFT')),
        submitted=Count('id', filter=Q(status='SUBMITTED')),
        confirmed=Count('id', filter=Q(status='CONFIRMED')),
        in_transit=Count('id', filter=Q(status='IN_TRANSIT')),
        completed=Count('id', filter=Q(status='COMPLETED')),
        cancelled=Count('id', filter=Q(status='CANCELLED')),
    )

    data = [
        ['Status', 'Count'],
        ['Total', str(stats['total'])],
        ['Draft', str(stats['draft'])],
        ['Submitted', str(stats['submitted'])],
        ['Confirmed', str(stats['confirmed'])],
        ['In Transit', str(stats['in_transit'])],
        ['Completed', str(stats['completed'])],
        ['Cancelled', str(stats['cancelled'])],
    ]
    table = Table(data, colWidths=[3 * inch, 2 * inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2A4A')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
    ]))
    elements.append(Paragraph('Booking Summary', styles['Heading2']))
    elements.append(table)

    # Top routes
    elements.append(Spacer(1, 0.3 * inch))
    routes = (bookings.values(
        origin=F('origin_port__code'), dest=F('destination_port__code'))
        .annotate(count=Count('id'))
        .order_by('-count')[:10])
    if routes:
        route_data = [['Origin', 'Destination', 'Bookings']]
        for r in routes:
            route_data.append([r['origin'] or '-', r['dest'] or '-', str(r['count'])])
        route_table = Table(route_data, colWidths=[2 * inch, 2 * inch, 1.5 * inch])
        route_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2A4A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(Paragraph('Top Routes', styles['Heading2']))
        elements.append(route_table)


def _add_carrier_section(elements, styles, bookings):
    """Add carrier performance data."""
    carriers = (bookings.exclude(carrier_name='')
                .values('carrier_name')
                .annotate(
                    total=Count('id'),
                    completed=Count('id', filter=Q(status='COMPLETED')),
                )
                .order_by('-total')[:15])
    if carriers:
        data = [['Carrier', 'Bookings', 'Completed']]
        for c in carriers:
            data.append([c['carrier_name'], str(c['total']), str(c['completed'])])
        table = Table(data, colWidths=[3 * inch, 1.5 * inch, 1.5 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2A4A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(Paragraph('Carrier Performance', styles['Heading2']))
        elements.append(table)
    else:
        elements.append(Paragraph('No carrier data for this period.', styles['Normal']))


def _add_volume_section(elements, styles, bookings):
    """Add volume by customer data."""
    customers = (bookings.values('customer__name', 'customer__code')
                 .annotate(
                     total=Count('id'),
                     total_weight=Avg('total_weight_kg'),
                 )
                 .order_by('-total')[:20])
    if customers:
        data = [['Customer', 'Code', 'Bookings', 'Avg Weight (kg)']]
        for c in customers:
            data.append([
                c['customer__name'] or '-',
                c['customer__code'] or '-',
                str(c['total']),
                f"{c['total_weight']:.0f}" if c['total_weight'] else '-',
            ])
        table = Table(data, colWidths=[2.5 * inch, 1 * inch, 1 * inch, 1.5 * inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E2A4A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(Paragraph('Volume by Customer', styles['Heading2']))
        elements.append(table)
    else:
        elements.append(Paragraph('No booking data for this period.', styles['Normal']))


def send_scheduled_reports():
    """Check all active scheduled reports and send any that are due."""
    from .models import ScheduledReport

    reports = ScheduledReport.objects.filter(is_active=True).select_related('organization')
    sent_count = 0
    errors = []

    for report in reports:
        if not _is_report_due(report):
            continue

        try:
            start_date, end_date = _get_date_range(report)
            pdf_buf = generate_report_pdf(
                report.organization, report.report_type, start_date, end_date)

            recipients = report.recipients
            if not recipients:
                continue

            subject = f'{report.name} — {report.organization.name}'
            body = (
                f'Please find attached your {report.get_frequency_display().lower()} '
                f'{report.get_report_type_display()} report.\n\n'
                f'Period: {start_date} to {end_date}'
            )

            email = EmailMessage(
                subject=subject,
                body=body,
                to=recipients,
            )
            filename = f'{report.report_type.lower()}_{start_date}_{end_date}.pdf'
            email.attach(filename, pdf_buf.read(), 'application/pdf')
            email.send(fail_silently=True)

            report.last_sent_at = timezone.now()
            report.save(update_fields=['last_sent_at'])
            sent_count += 1

        except Exception as e:
            errors.append(f'{report.name}: {e}')

    return sent_count, errors
