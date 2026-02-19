"""Tenant utilities for organization-scoped access.

Provides helper functions used throughout views, API, notifications,
and admin layers to enforce multi-tenant data isolation.
"""


def get_user_organization(user):
    """Return the Organization for a user, or None."""
    try:
        return user.profile.organization
    except (AttributeError, Exception):
        return None


def get_user_customer(user):
    """Return the Customer (Company) for a user, or None."""
    try:
        return user.profile.customer
    except (AttributeError, Exception):
        return None


def is_staff_for_org(user, organization):
    """Check if user is staff for a specific organization."""
    try:
        profile = user.profile
        return (
            profile.organization_id == organization.pk
            and profile.customer is None
        )
    except (AttributeError, Exception):
        return False


class TenantQuerySetMixin:
    """Mixin for class-based views that need tenant-scoped querysets.

    Usage:
        class MyView(TenantQuerySetMixin, ListView):
            def get_queryset(self):
                return self.scope_to_tenant(Booking.objects.all())
    """

    def get_organization(self):
        return get_user_organization(self.request.user)

    def scope_to_tenant(self, queryset, org_field='customer__organization'):
        """Filter queryset to the user's organization."""
        org = self.get_organization()
        if org:
            return queryset.filter(**{org_field: org})
        return queryset.none()
