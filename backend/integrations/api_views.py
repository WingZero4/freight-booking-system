"""API views for webhook subscription management and EDI upload."""
import logging

from rest_framework import viewsets, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.api_permissions import IsCustomerOrStaff
from .models import WebhookSubscription
from .serializers import WebhookSubscriptionSerializer, WebhookCreateSerializer

logger = logging.getLogger(__name__)


class WebhookSubscriptionViewSet(viewsets.ModelViewSet):
    """
    CRUD for webhook subscriptions.

    list:    GET    /api/v1/webhooks/
    create:  POST   /api/v1/webhooks/
    retrieve:GET    /api/v1/webhooks/{id}/
    destroy: DELETE /api/v1/webhooks/{id}/
    """
    permission_classes = [IsCustomerOrStaff]
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_queryset(self):
        user = self.request.user
        qs = WebhookSubscription.objects.select_related('customer')
        if not user.is_staff:
            profile = getattr(user, 'profile', None)
            if profile and profile.customer:
                qs = qs.filter(customer=profile.customer)
            else:
                qs = qs.none()
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return WebhookCreateSerializer
        return WebhookSubscriptionSerializer

    def perform_create(self, serializer):
        user = self.request.user
        if user.is_staff:
            customer_code = self.request.data.get('customer_code')
            if not customer_code:
                raise ValidationError(
                    {'customer_code': 'Staff must specify customer_code.'},
                )
            from bookings.models import Customer
            try:
                customer = Customer.objects.get(
                    code=customer_code, is_active=True,
                )
            except Customer.DoesNotExist:
                raise ValidationError(
                    {'customer_code': f'Customer "{customer_code}" not found.'},
                )
        else:
            profile = getattr(user, 'profile', None)
            customer = profile.customer if profile else None
            if not customer:
                raise ValidationError(
                    {'detail': 'A customer profile is required to create webhooks.'},
                )
        serializer.save(customer=customer, created_by=user)


class EDIUploadView(APIView):
    """
    POST /api/v1/edi/upload/ — Upload an EDIFACT IFTMBF file.

    Creates bookings from the EDI message.
    """
    permission_classes = [IsCustomerOrStaff]
    parser_classes = [MultiPartParser]

    def post(self, request):
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return Response(
                {'error': 'No file provided. Upload an EDI file as "file" field.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            content = uploaded_file.read().decode('utf-8', errors='replace')
        except Exception as e:
            return Response(
                {'error': f'Could not read file: {e}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Determine customer
        user = request.user
        if user.is_staff:
            customer_code = request.data.get('customer_code')
            if not customer_code:
                return Response(
                    {'error': 'Staff must specify customer_code.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from bookings.models import Customer
            try:
                customer = Customer.objects.get(
                    code=customer_code, is_active=True,
                )
            except Customer.DoesNotExist:
                return Response(
                    {'error': f'Customer "{customer_code}" not found.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            profile = getattr(user, 'profile', None)
            if not profile or not profile.customer:
                return Response(
                    {'error': 'Your account has no customer profile.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            customer = profile.customer

        from .edi.edi_service import process_edi_file
        result = process_edi_file(content, customer, user, request)

        http_status = (
            status.HTTP_201_CREATED if result['created']
            else status.HTTP_400_BAD_REQUEST
        )
        return Response(result, status=http_status)
