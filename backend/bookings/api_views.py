"""
DRF API views for the freight booking system.

Provides read-only booking endpoints + FMS callback endpoint.
"""
import logging

from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .api_permissions import IsCustomerOrStaff
from .models import Booking, BookingDocument
from .serializers import (
    BookingListSerializer,
    BookingDetailSerializer,
    BookingDocumentListSerializer,
    FMSCallbackSerializer,
)
from integrations.models import IntegrationLog

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint for bookings.

    list: GET /api/v1/bookings/ — paginated booking list
    retrieve: GET /api/v1/bookings/{id}/ — full booking detail
    callback: POST /api/v1/bookings/{id}/callback/ — FMS sends back refs
    documents: GET /api/v1/bookings/{id}/documents/ — list documents
    download: GET /api/v1/bookings/{id}/documents/{doc_id}/download/
    """
    permission_classes = [IsCustomerOrStaff]

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port', 'container_type',
        ).prefetch_related('items', 'booking_parties', 'documents')
        # Customer users only see their own bookings
        user = self.request.user
        if not user.is_staff:
            profile = getattr(user, 'profile', None)
            if profile and profile.customer:
                qs = qs.filter(customer=profile.customer)
            else:
                qs = qs.none()

        # Optional filters
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'].upper())
        if params.get('transport_mode'):
            qs = qs.filter(transport_mode=params['transport_mode'].upper())

        return qs

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return BookingDetailSerializer
        return BookingListSerializer

    @action(detail=True, methods=['post'], url_path='callback',
            permission_classes=[IsAdminUser])
    def callback(self, request, pk=None):
        """
        FMS callback endpoint — receives reference numbers from external FMS.

        POST /api/v1/bookings/{id}/callback/
        """
        booking = self.get_object()

        serializer = FMSCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Update booking FMS fields
        updated_fields = []
        for field in ['fms_shipment_id', 'hbl_number', 'mbl_number',
                      'hawb_number', 'mawb_number']:
            value = data.get(field, '')
            if value:
                setattr(booking, field, value)
                updated_fields.append(field)

        # Always mark callback received
        booking.fms_push_status = 'CALLBACK_RECEIVED'
        updated_fields.append('fms_push_status')
        booking.save(update_fields=updated_fields + ['updated_at'])

        # Log the callback with config link
        config = getattr(booking.customer, 'integration_config', None)
        IntegrationLog.objects.create(
            booking=booking,
            config=config,
            event='CALLBACK',
            adapter_type=config.adapter_type if config else '',
            response_payload=data,
        )

        logger.info(
            'FMS callback received for %s: %s',
            booking.booking_number, data
        )

        return Response(
            {'status': 'ok', 'booking_number': booking.booking_number},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['get'], url_path='documents')
    def documents(self, request, pk=None):
        """List documents for a booking."""
        booking = self.get_object()
        docs = booking.documents.all()
        serializer = BookingDocumentListSerializer(
            docs, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(
        detail=True, methods=['get'],
        url_path='documents/(?P<doc_id>[0-9]+)/download',
    )
    def download(self, request, pk=None, doc_id=None):
        """Download a specific document."""
        booking = self.get_object()
        document = get_object_or_404(
            BookingDocument, id=doc_id, booking=booking
        )
        return FileResponse(
            document.file.open('rb'),
            as_attachment=True,
            filename=document.original_filename,
        )
