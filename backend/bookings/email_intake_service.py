"""Email-to-Booking AI service — process inbound emails into draft bookings."""

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def match_sender_to_customer(sender_email):
    """Match an email sender to a Customer by email or user lookup.

    Returns (customer, user) tuple or (None, None).
    """
    from django.contrib.auth.models import User
    from .models import Customer, UserProfile

    # Try exact user email match
    try:
        user = User.objects.get(email__iexact=sender_email, is_active=True)
        profile = getattr(user, 'profile', None)
        if profile and profile.customer:
            return profile.customer, user
    except User.DoesNotExist:
        pass

    # Try domain match against customer email
    domain = sender_email.split('@')[-1].lower()
    customer = Customer.objects.filter(
        email__iendswith=f'@{domain}', is_active=True
    ).first()
    if customer:
        return customer, None

    return None, None


def extract_booking_from_email(body):
    """Use Claude to extract booking fields from email body text.

    Returns dict of extracted fields or None on failure.
    """
    import json
    import os
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning('openai package not installed')
        return None

    api_key = os.environ.get('OPENAI_API_KEY', '')
    if not api_key:
        logger.warning('OPENAI_API_KEY not set')
        return None

    client = OpenAI(api_key=api_key)

    prompt = """Extract booking request fields from this email. Return JSON with:
{
    "port_of_loading": "",
    "port_of_discharge": "",
    "cargo_description": "",
    "total_weight_kg": null,
    "total_volume_cbm": null,
    "container_type": "",
    "transport_mode": "",
    "incoterms": "",
    "etd_requested": "",
    "shipper": {"name": "", "address": ""},
    "consignee": {"name": "", "address": ""},
    "special_instructions": "",
    "booking_reference": ""
}
Only include fields that are clearly stated in the email. Use null for missing numeric fields and empty string for missing text fields."""

    try:
        response = client.chat.completions.create(
            model='gpt-4.1-nano',
            messages=[
                {'role': 'system', 'content': prompt},
                {'role': 'user', 'content': body[:8000]},
            ],
            response_format={'type': 'json_object'},
            temperature=0.1,
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception as e:
        logger.error('Email extraction failed: %s', e)
        return None


def create_draft_from_extraction(extracted, customer, user=None):
    """Create a DRAFT booking from extracted email data.

    Returns (booking, errors_list).
    """
    from .models import Booking, Port
    from .document_booking_service import _resolve_port

    errors = []

    booking = Booking(
        customer=customer,
        status='DRAFT',
        source_channel='EMAIL',
    )

    # Port resolution
    pol = extracted.get('port_of_loading', '')
    pod = extracted.get('port_of_discharge', '')
    if pol:
        port_id = _resolve_port(pol)
        if port_id:
            booking.origin_port_id = port_id
        else:
            errors.append(f'Could not resolve port of loading: {pol}')
    if pod:
        port_id = _resolve_port(pod)
        if port_id:
            booking.destination_port_id = port_id
        else:
            errors.append(f'Could not resolve port of discharge: {pod}')

    # Simple fields
    cargo_desc = extracted.get('cargo_description', '')
    if cargo_desc:
        booking.commodity_description = cargo_desc

    incoterms = extracted.get('incoterms', '')
    if incoterms:
        booking.incoterms = incoterms.upper()

    instructions = extracted.get('special_instructions', '')
    if instructions:
        booking.special_instructions = instructions

    ref = extracted.get('booking_reference', '')
    if ref:
        booking.external_reference = ref

    weight = extracted.get('total_weight_kg')
    if weight:
        try:
            booking.total_weight_kg = float(weight)
        except (ValueError, TypeError):
            pass

    volume = extracted.get('total_volume_cbm')
    if volume:
        try:
            booking.total_volume_cbm = float(volume)
        except (ValueError, TypeError):
            pass

    # Transport mode
    mode = extracted.get('transport_mode', '')
    if mode:
        mode_upper = mode.upper().replace(' ', '_')
        valid_modes = [
            'SEA_FCL', 'SEA_LCL', 'AIR', 'RAIL', 'TRUCK',
            'SEA_AIR', 'AIR_SEA', 'MULTIMODAL',
        ]
        if mode_upper in valid_modes:
            booking.transport_mode = mode_upper

    if user:
        booking.created_by = user

    booking.save()
    return booking, errors


def process_inbound_email(sender, subject, body, attachments=None):
    """Main orchestrator: process an inbound email into a draft booking.

    Returns dict with status and details.
    """
    from .models import InboundEmail
    from .feature_service import FeatureFlagService

    # Record the inbound email
    record = InboundEmail.objects.create(
        sender=sender,
        subject=subject,
        body=body[:50000],
    )

    # Match sender
    customer, user = match_sender_to_customer(sender)
    if not customer:
        record.status = 'FAILED'
        record.error_message = f'No customer found for sender: {sender}'
        record.save(update_fields=['status', 'error_message'])
        return {'status': 'FAILED', 'error': record.error_message}

    record.customer = customer
    record.save(update_fields=['customer'])

    # Check feature flag
    org = customer.organization
    if not FeatureFlagService.is_enabled(org, 'enable_email_to_booking'):
        record.status = 'FAILED'
        record.error_message = 'Email-to-booking not enabled for this organization'
        record.save(update_fields=['status', 'error_message'])
        return {'status': 'FAILED', 'error': record.error_message}

    # Extract booking data from email
    extracted = extract_booking_from_email(body)
    if not extracted:
        record.status = 'FAILED'
        record.error_message = 'AI extraction returned no data'
        record.save(update_fields=['status', 'error_message'])
        return {'status': 'FAILED', 'error': record.error_message}

    # Create draft booking
    booking, errors = create_draft_from_extraction(extracted, customer, user)
    record.booking = booking
    record.status = 'PROCESSED'
    if errors:
        record.error_message = '; '.join(errors)
    record.save(update_fields=['booking', 'status', 'error_message'])

    # Notify ops about new email-to-booking draft
    try:
        from .notifications import notify_ops_new_booking
        notify_ops_new_booking(booking)
    except Exception as e:
        logger.error('Failed to notify ops about email booking: %s', e)

    return {
        'status': 'PROCESSED',
        'booking_id': booking.id,
        'booking_number': booking.booking_number,
        'errors': errors,
    }
