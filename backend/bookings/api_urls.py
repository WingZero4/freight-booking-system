"""
API URL routing for the freight booking system.

All endpoints are under /api/v1/.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import BookingViewSet
from integrations.api_views import WebhookSubscriptionViewSet, EDIUploadView

router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'webhooks', WebhookSubscriptionViewSet, basename='webhook')

urlpatterns = [
    path('', include(router.urls)),
    path('edi/upload/', EDIUploadView.as_view(), name='edi-upload'),
]
