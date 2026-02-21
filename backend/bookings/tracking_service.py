"""Real-time vessel/container tracking service."""

import logging
import os

from django.utils import timezone

logger = logging.getLogger(__name__)

TRACKING_API_KEY = os.environ.get('TRACKING_API_KEY', '')
TRACKING_API_PROVIDER = os.environ.get('TRACKING_API_PROVIDER', 'manual')


def get_vessel_position(vessel_name, imo_number=None):
    """Query tracking API for current vessel position.

    Returns dict with lat, lng, speed, heading, destination, eta or None.
    """
    from .models import VesselPosition

    if not TRACKING_API_KEY or TRACKING_API_PROVIDER == 'manual':
        # Return cached position if available
        vp = VesselPosition.objects.filter(vessel_name__iexact=vessel_name).first()
        if vp:
            return {
                'vessel_name': vp.vessel_name,
                'latitude': vp.latitude,
                'longitude': vp.longitude,
                'speed_knots': vp.speed_knots,
                'heading': vp.heading,
                'destination': vp.destination,
                'eta': vp.eta,
                'updated_at': vp.updated_at,
            }
        return None

    # API integration placeholder — implement when API key configured
    # Supports: dcsa, marinetraffic, searates
    logger.info('Tracking API call for vessel %s (provider: %s)',
                vessel_name, TRACKING_API_PROVIDER)
    return None


def get_container_status(container_number, carrier_code=None):
    """Query tracking API for container milestone data.

    Returns list of event dicts or empty list.
    """
    if not TRACKING_API_KEY or TRACKING_API_PROVIDER == 'manual':
        return []

    logger.info('Container tracking API call for %s (provider: %s)',
                container_number, TRACKING_API_PROVIDER)
    return []


def update_booking_tracking(booking):
    """Refresh tracking data for a single booking.

    Creates TrackingEvent records from API data.
    Returns number of new events created.
    """
    from .models import TrackingEvent, VesselPosition

    new_events = 0

    # Try vessel tracking
    if booking.vessel_name:
        position = get_vessel_position(booking.vessel_name)
        if position and position.get('latitude'):
            VesselPosition.objects.update_or_create(
                vessel_name=booking.vessel_name,
                defaults={
                    'latitude': position['latitude'],
                    'longitude': position['longitude'],
                    'speed_knots': position.get('speed_knots'),
                    'heading': position.get('heading'),
                    'destination': position.get('destination'),
                    'eta': position.get('eta'),
                },
            )

    # Try container tracking for each item with container numbers
    for item in booking.items.all():
        if not item.marks_and_numbers:
            continue
        # Marks field may contain container numbers
        container = item.marks_and_numbers.strip()
        if len(container) != 11:
            continue  # Standard container numbers are 11 chars

        events = get_container_status(container)
        for event_data in events:
            occurred_at = event_data.get('occurred_at')
            event_type = event_data.get('event_type', 'UNKNOWN')
            if not occurred_at:
                continue

            # Avoid duplicates
            exists = TrackingEvent.objects.filter(
                booking=booking,
                event_type=event_type,
                occurred_at=occurred_at,
            ).exists()
            if not exists:
                TrackingEvent.objects.create(
                    booking=booking,
                    event_type=event_type,
                    location=event_data.get('location', ''),
                    vessel_name=event_data.get('vessel_name', ''),
                    occurred_at=occurred_at,
                    source='API',
                    raw_data=event_data,
                )
                new_events += 1

    return new_events


def bulk_update_tracking():
    """Refresh tracking for all active bookings.

    Only refreshes IN_TRANSIT and ARRIVED bookings.
    Returns (updated_count, errors).
    """
    from .models import Booking

    bookings = Booking.objects.filter(
        status__in=['IN_TRANSIT', 'ARRIVED'],
    ).exclude(
        vessel_name='',
    )

    updated = 0
    errors = []

    for booking in bookings:
        try:
            new_events = update_booking_tracking(booking)
            if new_events > 0:
                updated += 1
        except Exception as e:
            errors.append(f'{booking.booking_number}: {e}')

    return updated, errors


def get_tracking_timeline(booking):
    """Get merged timeline of tracking events and shipment milestones.

    Returns list of dicts sorted by timestamp, newest first.
    """
    from .models import TrackingEvent, ShipmentMilestone

    timeline = []

    # Add tracking events
    for event in booking.tracking_events.all():
        timeline.append({
            'type': 'tracking',
            'timestamp': event.occurred_at,
            'event': event.event_type,
            'location': event.location,
            'vessel': event.vessel_name,
            'source': event.get_source_display(),
        })

    # Add shipment milestones
    for milestone in booking.milestones.all():
        timeline.append({
            'type': 'milestone',
            'timestamp': milestone.occurred_at,
            'event': milestone.get_event_type_display(),
            'location': milestone.location or '',
            'vessel': milestone.vessel_name or '',
            'source': 'System',
            'notes': milestone.notes,
        })

    # Sort by timestamp descending
    timeline.sort(key=lambda x: x['timestamp'], reverse=True)
    return timeline
