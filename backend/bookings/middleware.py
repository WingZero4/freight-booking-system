"""Custom middleware for the bookings application."""
import zoneinfo

from django.utils import timezone


class TimezoneMiddleware:
    """Activate the authenticated user's preferred timezone for each request.

    If the user has no timezone set or the value is invalid, falls back to
    UTC (the Django default).  Must be placed AFTER AuthenticationMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, 'profile', None)
            tz_name = getattr(profile, 'timezone', '') if profile else ''
            if tz_name:
                try:
                    timezone.activate(zoneinfo.ZoneInfo(tz_name))
                except (zoneinfo.ZoneInfoNotFoundError, KeyError):
                    timezone.deactivate()
            else:
                timezone.deactivate()
        else:
            timezone.deactivate()

        response = self.get_response(request)
        timezone.deactivate()  # Clean up for WSGI thread reuse
        return response
