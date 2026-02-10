def nav_active(request):
    """Set the active navigation item based on the current URL path."""
    path = request.path
    if path.startswith('/ops/'):
        return {'nav_active': 'ops'}
    elif path == '/bookings/create/':
        return {'nav_active': 'new_booking'}
    elif path.startswith('/bookings/import'):
        return {'nav_active': 'import'}
    elif path.startswith('/bookings/'):
        return {'nav_active': 'bookings'}
    elif path.startswith('/parties/'):
        return {'nav_active': 'parties'}
    elif path == '/':
        return {'nav_active': 'dashboard'}
    return {'nav_active': ''}


def customer_theme(request):
    """Inject customer branding into template context.

    Returns CSS custom property values and branding info.
    Falls back to default Navy+Crimson theme when no customer branding is set.
    """
    defaults = {
        'theme_primary': '#1E2A4A',
        'theme_accent': '#DC3545',
        'theme_portal_name': 'Freight Booking',
        'theme_logo_url': '',
    }
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return defaults
    try:
        from bookings.models import UserProfile
        profile = UserProfile.objects.select_related('customer').get(user=request.user)
        if profile.customer:
            c = profile.customer
            if c.primary_color:
                defaults['theme_primary'] = c.primary_color
            if c.accent_color:
                defaults['theme_accent'] = c.accent_color
            if c.portal_name:
                defaults['theme_portal_name'] = c.portal_name
            if c.logo:
                defaults['theme_logo_url'] = c.logo.url
    except Exception:
        pass
    return defaults
