def nav_active(request):
    """Set the active navigation item based on the current URL path."""
    path = request.path
    if path.startswith('/ops/'):
        return {'nav_active': 'ops'}
    elif path == '/bookings/create/':
        return {'nav_active': 'new_booking'}
    elif path.startswith('/bookings/'):
        return {'nav_active': 'bookings'}
    elif path.startswith('/parties/'):
        return {'nav_active': 'parties'}
    elif path == '/':
        return {'nav_active': 'dashboard'}
    return {'nav_active': ''}
