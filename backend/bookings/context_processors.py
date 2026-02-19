def nav_active(request):
    """Set the active navigation item based on the current URL path."""
    path = request.path
    context = {}
    if path.startswith('/ops/users'):
        context['nav_active'] = 'users'
    elif path.startswith('/ops/reports'):
        context['nav_active'] = 'reports'
    elif path.startswith('/ops/'):
        context['nav_active'] = 'dashboard'
    elif path.startswith('/profile/'):
        context['nav_active'] = 'profile'
    elif path.startswith('/notifications/'):
        context['nav_active'] = 'notifications'
    elif path.startswith('/templates/'):
        context['nav_active'] = 'templates'
    elif path == '/bookings/create/':
        context['nav_active'] = 'new_booking'
    elif path.startswith('/bookings/import'):
        context['nav_active'] = 'import'
    elif path.startswith('/consolidations/'):
        context['nav_active'] = 'consolidations'
    elif path.startswith('/reports/'):
        context['nav_active'] = 'reports'
    elif path.startswith('/bookings/'):
        context['nav_active'] = 'bookings'
    elif path.startswith('/parties/'):
        context['nav_active'] = 'parties'
    elif path == '/':
        context['nav_active'] = 'dashboard'
    else:
        context['nav_active'] = ''

    # Pending registrations badge for staff nav (scoped to org)
    if hasattr(request, 'user') and request.user.is_authenticated:
        try:
            profile = request.user.profile
            if not profile.customer:  # staff/ops user
                from bookings.models import UserProfile
                filters = {'approval_status': 'PENDING'}
                if profile.organization_id:
                    filters['organization'] = profile.organization
                context['pending_registrations_count'] = UserProfile.objects.filter(
                    **filters
                ).count()
        except Exception:
            pass

    return context


def notifications_context(request):
    """Inject unread notification count and recent notifications into template context."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}
    from bookings.models import Notification
    user_notifications = Notification.objects.filter(user=request.user)
    return {
        'unread_notifications_count': user_notifications.filter(is_read=False).count(),
        'recent_notifications': user_notifications.select_related('booking')[:5],
    }


def customer_theme(request):
    """Inject customer branding into template context.

    Resolution order: Customer branding > Organization branding > System defaults.
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
        profile = UserProfile.objects.select_related(
            'customer', 'organization').get(user=request.user)
        # Layer 1: Organization branding (fallback for staff)
        if profile.organization:
            org = profile.organization
            if org.primary_color:
                defaults['theme_primary'] = org.primary_color
            if org.accent_color:
                defaults['theme_accent'] = org.accent_color
            if org.portal_name:
                defaults['theme_portal_name'] = org.portal_name
            if org.logo:
                defaults['theme_logo_url'] = org.logo.url
        # Layer 2: Customer branding (overrides org for customer users)
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
