"""
API permissions for customer-scoped access.

API tokens are tied to users who belong to a customer. Each API user
can only see/modify bookings belonging to their own customer.
Staff users can see all bookings.
"""
from rest_framework.permissions import BasePermission


class IsCustomerOrStaff(BasePermission):
    """
    Allow access if the user is staff or has a customer profile.
    Customer users only see their own customer's bookings.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        # Staff can do everything
        if request.user.is_staff:
            return True
        # Customer users must have a profile with a customer
        profile = getattr(request.user, 'profile', None)
        return profile is not None and profile.customer is not None

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        profile = getattr(request.user, 'profile', None)
        if profile is None:
            return False
        # obj is a Booking — check customer match
        return obj.customer_id == profile.customer_id
