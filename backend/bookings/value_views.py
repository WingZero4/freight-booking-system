"""Views for value enhancement features (10 features)."""

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, FileResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.utils import timezone

from .models import (
    Booking, Party, BookingComment, ScheduledReport,
    SLAConfig, SLABreach, ScreeningResult, TrackingEvent,
    InboundEmail,
)
from .feature_service import FeatureFlagService
from .tenant import get_user_organization, get_user_customer_ids


def _is_staff(user):
    return user.is_staff or not getattr(getattr(user, 'profile', None), 'customer', None)


def _get_org(user):
    return get_user_organization(user)


# ─── Feature 1: Sanctions Screening ──────────────────────────────────

@login_required
@require_POST
def party_screen(request, party_id):
    """Manual re-screen a party against sanctions lists."""
    party = get_object_or_404(Party, pk=party_id)
    org = _get_org(request.user)

    if not FeatureFlagService.is_enabled(org, 'enable_sanctions_screening'):
        return JsonResponse({'error': 'Sanctions screening not enabled'}, status=403)

    from .screening_service import screen_party
    results = screen_party(party)

    data = []
    for r in results:
        data.append({
            'list': r.list_checked,
            'status': r.status,
            'score': r.match_score,
            'details': r.match_details,
        })

    return JsonResponse({'party': party.company_name, 'results': data})


@login_required
def screening_review(request, result_id):
    """Staff review of a potential match screening result."""
    if not _is_staff(request.user):
        messages.error(request, 'Staff access required.')
        return redirect('dashboard')

    result = get_object_or_404(ScreeningResult, pk=result_id)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'clear':
            result.status = 'REVIEWED_OK'
        elif action == 'block':
            result.status = 'REVIEWED_BLOCKED'
        result.reviewed_by = request.user
        result.reviewed_at = timezone.now()
        result.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
        messages.success(request, f'Screening result updated to {result.get_status_display()}.')
        return redirect('party_list')

    return render(request, 'bookings/screening_review.html', {
        'result': result,
    })


# ─── Feature 2: Scheduled Reports ────────────────────────────────────

@login_required
def scheduled_report_list(request):
    """List scheduled reports for current org."""
    if not _is_staff(request.user):
        messages.error(request, 'Staff access required.')
        return redirect('dashboard')

    org = _get_org(request.user)
    reports = ScheduledReport.objects.filter(organization=org)

    return render(request, 'bookings/scheduled_report_list.html', {
        'reports': reports,
        'nav_active': 'reports',
    })


@login_required
def scheduled_report_create(request):
    """Create a new scheduled report."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    org = _get_org(request.user)
    if not FeatureFlagService.is_enabled(org, 'enable_scheduled_reports'):
        messages.error(request, 'Scheduled reports not enabled.')
        return redirect('ops_reports_hub')

    if request.method == 'POST':
        report = ScheduledReport(
            organization=org,
            created_by=request.user,
        )
        report.name = request.POST.get('name', '')
        report.report_type = request.POST.get('report_type', 'WEEKLY_SUMMARY')
        report.frequency = request.POST.get('frequency', 'WEEKLY')
        report.hour = int(request.POST.get('hour', 7))

        day_of_week = request.POST.get('day_of_week', '')
        if day_of_week:
            report.day_of_week = int(day_of_week)
        day_of_month = request.POST.get('day_of_month', '')
        if day_of_month:
            report.day_of_month = int(day_of_month)

        recipients_text = request.POST.get('recipients', '')
        report.recipients = [
            e.strip() for e in recipients_text.split(',') if e.strip()
        ]

        report.save()
        messages.success(request, f'Scheduled report "{report.name}" created.')
        return redirect('scheduled_report_list')

    return render(request, 'bookings/scheduled_report_form.html', {
        'report': None,
        'report_types': ScheduledReport.REPORT_TYPE_CHOICES,
        'frequency_choices': ScheduledReport.FREQUENCY_CHOICES,
        'nav_active': 'reports',
    })


@login_required
def scheduled_report_edit(request, report_id):
    """Edit a scheduled report."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    report = get_object_or_404(ScheduledReport, pk=report_id)

    if request.method == 'POST':
        report.name = request.POST.get('name', report.name)
        report.report_type = request.POST.get('report_type', report.report_type)
        report.frequency = request.POST.get('frequency', report.frequency)
        report.hour = int(request.POST.get('hour', report.hour))
        report.is_active = request.POST.get('is_active') == 'on'

        day_of_week = request.POST.get('day_of_week', '')
        report.day_of_week = int(day_of_week) if day_of_week else None
        day_of_month = request.POST.get('day_of_month', '')
        report.day_of_month = int(day_of_month) if day_of_month else None

        recipients_text = request.POST.get('recipients', '')
        report.recipients = [
            e.strip() for e in recipients_text.split(',') if e.strip()
        ]

        report.save()
        messages.success(request, f'Report "{report.name}" updated.')
        return redirect('scheduled_report_list')

    return render(request, 'bookings/scheduled_report_form.html', {
        'report': report,
        'report_types': ScheduledReport.REPORT_TYPE_CHOICES,
        'frequency_choices': ScheduledReport.FREQUENCY_CHOICES,
        'nav_active': 'reports',
    })


@login_required
@require_POST
def scheduled_report_delete(request, report_id):
    """Delete a scheduled report."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    report = get_object_or_404(ScheduledReport, pk=report_id)
    name = report.name
    report.delete()
    messages.success(request, f'Report "{name}" deleted.')
    return redirect('scheduled_report_list')


# ─── Feature 3: Booking Comments ─────────────────────────────────────

@login_required
@require_POST
def booking_comment_add(request, booking_id):
    """Add a comment to a booking (AJAX endpoint)."""
    booking = get_object_or_404(Booking, pk=booking_id)
    org = _get_org(request.user)

    if not FeatureFlagService.is_enabled(org, 'enable_booking_comments'):
        return JsonResponse({'error': 'Comments not enabled'}, status=403)

    # Permission check: staff or customer user for this booking
    if not _is_staff(request.user):
        customer_ids = get_user_customer_ids(request.user)
        if booking.customer_id not in customer_ids:
            return JsonResponse({'error': 'Access denied'}, status=403)

    message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({'error': 'Message is required'}, status=400)
    if len(message) > 5000:
        return JsonResponse({'error': 'Message too long (max 5000 chars)'}, status=400)

    is_internal = request.POST.get('is_internal') == 'true' and _is_staff(request.user)

    comment = BookingComment.objects.create(
        booking=booking,
        author=request.user,
        message=message,
        is_internal=is_internal,
    )

    # Send notifications
    try:
        from .notifications import notify_booking_comment
        notify_booking_comment(comment)
    except Exception:
        pass

    return JsonResponse({
        'id': comment.id,
        'author': comment.author.get_full_name() or comment.author.username,
        'message': comment.message,
        'is_internal': comment.is_internal,
        'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
    })


@login_required
@require_GET
def booking_comments_list(request, booking_id):
    """Get comments for a booking (AJAX endpoint)."""
    booking = get_object_or_404(Booking, pk=booking_id)

    # Permission check
    if not _is_staff(request.user):
        customer_ids = get_user_customer_ids(request.user)
        if booking.customer_id not in customer_ids:
            return JsonResponse({'error': 'Access denied'}, status=403)

    comments = booking.comments.select_related('author').all()
    if not _is_staff(request.user):
        comments = comments.filter(is_internal=False)

    data = []
    for c in comments:
        data.append({
            'id': c.id,
            'author': c.author.get_full_name() or c.author.username,
            'message': c.message,
            'is_internal': c.is_internal,
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M'),
        })

    return JsonResponse({'comments': data})


# ─── Feature 4: SLA Management ───────────────────────────────────────

@login_required
def sla_config_list(request):
    """List SLA configurations for current org."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    org = _get_org(request.user)
    configs = SLAConfig.objects.filter(organization=org)
    breaches = SLABreach.objects.filter(
        booking__customer__organization=org,
        resolved_at__isnull=True,
    ).select_related('booking', 'sla_config')[:20]

    return render(request, 'bookings/sla_config_list.html', {
        'configs': configs,
        'breaches': breaches,
        'nav_active': 'workflows',
    })


@login_required
def sla_config_edit(request, config_id=None):
    """Create or edit an SLA config."""
    if not _is_staff(request.user):
        return redirect('dashboard')

    org = _get_org(request.user)
    config = None
    if config_id:
        config = get_object_or_404(SLAConfig, pk=config_id, organization=org)

    if request.method == 'POST':
        if not config:
            config = SLAConfig(organization=org)

        config.status = request.POST.get('status', '')
        config.max_hours = int(request.POST.get('max_hours', 24))
        config.warning_pct = int(request.POST.get('warning_pct', 75))
        config.escalation_email = request.POST.get('escalation_email', '')
        config.escalation_action = request.POST.get('escalation_action', 'BOTH')
        config.is_active = request.POST.get('is_active') == 'on'
        config.save()

        messages.success(request, 'SLA configuration saved.')
        return redirect('sla_config_list')

    status_choices = [
        ('SUBMITTED', 'Submitted'),
        ('CONFIRMED', 'Confirmed'),
        ('PACKING', 'Packing'),
        ('IN_TRANSIT', 'In Transit'),
        ('ARRIVED', 'Arrived'),
    ]

    return render(request, 'bookings/sla_config_form.html', {
        'config': config,
        'status_choices': status_choices,
        'escalation_choices': SLAConfig.ESCALATION_CHOICES,
        'nav_active': 'workflows',
    })


# ─── Feature 5: Auto-Quote from Rate Sheets ──────────────────────────

@login_required
@require_GET
def rate_quote_api(request):
    """AJAX endpoint: get matching rates for given parameters."""
    org = _get_org(request.user)

    if not FeatureFlagService.is_enabled(org, 'enable_auto_quoting'):
        return JsonResponse({'error': 'Auto-quoting not enabled'}, status=403)

    origin = request.GET.get('origin')
    dest = request.GET.get('dest')
    mode = request.GET.get('mode', '')
    container = request.GET.get('container', '')

    if not origin or not dest:
        return JsonResponse({'rates': [], 'message': 'Select origin and destination.'})

    from .quoting_service import get_rates_for_booking_form
    rates = get_rates_for_booking_form(
        origin_port_id=origin,
        destination_port_id=dest,
        transport_mode=mode or None,
        container_type_id=container or None,
    )

    return JsonResponse({
        'rates': rates,
        'message': '' if rates else 'No rates available for this route.',
    })


# ─── Feature 7: Create Booking from Document ─────────────────────────

@login_required
def booking_create_from_document(request):
    """Upload a PDF to pre-populate a new booking form."""
    org = _get_org(request.user)

    if not FeatureFlagService.is_enabled(org, 'enable_document_to_booking'):
        messages.error(request, 'Document-to-booking not enabled.')
        return redirect('dashboard')

    if request.method == 'POST' and request.FILES.get('document'):
        from .document_booking_service import (
            extract_booking_data_from_pdf, map_extracted_to_form_data,
        )
        import tempfile
        import os

        uploaded = request.FILES['document']

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        try:
            extracted, error = extract_booking_data_from_pdf(tmp_path)
            if error:
                messages.error(request, f'Extraction failed: {error}')
                return redirect('booking_create_from_document')

            mapped = map_extracted_to_form_data(extracted)

            # Store in session for the booking form
            request.session['doc_booking_data'] = mapped
            messages.success(request, 'Document extracted. Review and save the booking below.')
            return redirect('booking_create')
        finally:
            os.unlink(tmp_path)

    return render(request, 'bookings/create_from_document.html', {
        'nav_active': 'bookings',
    })


# ─── Feature 8: Email-to-Booking Webhook ─────────────────────────────

@csrf_exempt
@require_POST
def inbound_email_webhook(request):
    """Webhook endpoint for inbound email processing (SendGrid/Mailgun)."""
    from .email_intake_service import process_inbound_email

    sender = request.POST.get('from', request.POST.get('sender', ''))
    subject = request.POST.get('subject', '')
    body = request.POST.get('text', request.POST.get('body-plain', ''))

    if not sender or not body:
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    result = process_inbound_email(sender, subject, body)
    return JsonResponse(result)


# ─── Feature 9: Draft HBL Generation ─────────────────────────────────

@login_required
def draft_hbl_view(request, booking_id):
    """Generate and download a draft HBL PDF."""
    booking = get_object_or_404(
        Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port'),
        pk=booking_id,
    )

    org = _get_org(request.user)
    if not FeatureFlagService.is_enabled(org, 'enable_hbl_generation'):
        messages.error(request, 'HBL generation not enabled.')
        return redirect('booking_detail', booking_id=booking_id)

    # Only available for CONFIRMED and later statuses
    if booking.status in ('DRAFT', 'SUBMITTED'):
        messages.warning(request, 'HBL only available for confirmed or later bookings.')
        return redirect('booking_detail', booking_id=booking_id)

    from .hbl_generator import generate_draft_hbl
    pdf_buf = generate_draft_hbl(booking)

    filename = f'DRAFT_HBL_{booking.booking_number}.pdf'
    response = HttpResponse(pdf_buf.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─── Feature 10: Tracking ────────────────────────────────────────────

@login_required
def booking_tracking(request, booking_id):
    """Tracking timeline and map view for a booking."""
    booking = get_object_or_404(
        Booking.objects.select_related('origin_port', 'destination_port'),
        pk=booking_id,
    )

    org = _get_org(request.user)
    if not FeatureFlagService.is_enabled(org, 'enable_tracking'):
        messages.error(request, 'Tracking not enabled.')
        return redirect('booking_detail', booking_id=booking_id)

    from .tracking_service import get_tracking_timeline, get_vessel_position
    timeline = get_tracking_timeline(booking)
    vessel_position = None
    if booking.vessel_name:
        vessel_position = get_vessel_position(booking.vessel_name)

    return render(request, 'bookings/tracking.html', {
        'booking': booking,
        'timeline': timeline,
        'vessel_position': vessel_position,
        'nav_active': 'bookings',
    })


@login_required
@require_POST
def tracking_refresh(request, booking_id):
    """Force refresh tracking data from API."""
    booking = get_object_or_404(Booking, pk=booking_id)

    from .tracking_service import update_booking_tracking
    new_events = update_booking_tracking(booking)

    messages.success(request, f'Tracking refreshed. {new_events} new event(s) found.')
    return redirect('booking_tracking', booking_id=booking_id)
