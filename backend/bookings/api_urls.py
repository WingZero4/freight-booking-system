"""
API URL routing for the freight booking system.

All endpoints are under /api/v1/.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import BookingViewSet

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')

urlpatterns = [
    path('', include(router.urls)),
]
