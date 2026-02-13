def nav_active(request):
    """Set the active navigation item based on the current URL path."""
    path = request.path
    context = {}
    if path.startswith('/ops/users'):
        context['nav_active'] = 'users'
    elif path.startswith('/ops/'):
        context['nav_active'] = 'dashboard'
    elif path == '/bookings/create/':
        context['nav_active'] = 'new_booking'
    elif path.startswith('/bookings/import'):
        context['nav_active'] = 'import'
    elif path.startswith('/bookings/'):
        context['nav_active'] = 'bookings'
    elif path.startswith('/parties/'):
        context['nav_active'] = 'parties'
    elif path == '/':
        context['nav_active'] = 'dashboard'
    else:
        context['nav_active'] = ''

    # Pending registrations badge for staff nav
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            profile = request.user.profile
            if not profile.customer:  # staff/ops user
                from bookings.models import UserProfile
                context['pending_registrations_count'] = UserProfile.objects.filter(
                    approval_status='PENDING'
                ).count()
        except Exception:
            pass

    return context


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
