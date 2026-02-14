"""
API URL routing for the freight booking system.

All endpoints are under /api/v1/.
"""
from django.urls import path, include
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.routers import DefaultRouter
from rest_framework.throttling import AnonRateThrottle

from .api_views import BookingViewSet
from integrations.api_views import WebhookSubscriptionViewSet, EDIUploadView


class TokenObtainThrottle(AnonRateThrottle):
    scope = 'token_obtain'


class ThrottledObtainAuthToken(ObtainAuthToken):
    throttle_classes = [TokenObtainThrottle]


router = DefaultRouter()
router.register(r'bookings', BookingViewSet, basename='booking')
router.register(r'webhooks', WebhookSubscriptionViewSet, basename='webhook')

urlpatterns = [
    path('token/', ThrottledObtainAuthToken.as_view(), name='api-token-auth'),
    path('', include(router.urls)),
    path('edi/upload/', EDIUploadView.as_view(), name='edi-upload'),
]
