"""
DRF API views for the freight booking system.

Provides full booking CRUD + status transitions + FMS/carrier callbacks.
"""
import logging

from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .api_filters import BookingFilter
from .api_permissions import IsCustomerOrStaff
from .models import Booking, BookingDocument, Customer
from .serializers import (
    BookingListSerializer,
    BookingDetailSerializer,
    BookingDocumentListSerializer,
    FMSCallbackSerializer,
    CarrierCallbackSerializer,
    BookingCreateSerializer,
    BookingUpdateSerializer,
    DocumentUploadSerializer,
)
from .services import BookingService
from integrations.models import IntegrationLog

logger = logging.getLogger(__name__)


class BookingViewSet(viewsets.ModelViewSet):
    """
    API endpoint for bookings.

    list:    GET    /api/v1/bookings/
    create:  POST   /api/v1/bookings/
    retrieve:GET    /api/v1/bookings/{id}/
    partial_update: PATCH /api/v1/bookings/{id}/
    submit:  POST   /api/v1/bookings/{id}/submit/
    cancel:  POST   /api/v1/bookings/{id}/cancel/
    documents: GET/POST /api/v1/bookings/{id}/documents/
    download:  GET  /api/v1/bookings/{id}/documents/{doc_id}/download/
    callback:  POST /api/v1/bookings/{id}/callback/
    carrier_callback: POST /api/v1/bookings/{id}/carrier-callback/
    """
    permission_classes = [IsCustomerOrStaff]
    # No PUT — only PATCH for partial updates
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_class = BookingFilter
    ordering_fields = [
        'created_at', 'cargo_ready_date', 'status', 'booking_number',
    ]
    ordering = ['-created_at']

    def get_queryset(self):
        qs = Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port', 'container_type',
            'carrier_config',
        ).prefetch_related('items', 'booking_parties', 'documents')
        # Customer users only see their own bookings
        user = self.request.user
        if not user.is_staff:
            profile = getattr(user, 'profile', None)
            if profile and profile.customer:
                qs = qs.filter(customer=profile.customer)
            else:
                qs = qs.none()
        return qs

    def get_serializer_class(self):
        if self.action == 'create':
            return BookingCreateSerializer
        if self.action == 'partial_update':
            return BookingUpdateSerializer
        if self.action == 'retrieve':
            return BookingDetailSerializer
        return BookingListSerializer

    # ─── Create ─────────────────────────────────────────────────

    def create(self, request):
        """POST /api/v1/bookings/ — Create a new booking with cargo items."""
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Idempotency check
        idempotency_key = data.pop('idempotency_key', None)
        if idempotency_key:
            cache_key = f'idempotent:{request.user.pk}:{idempotency_key}'
            cached_id = cache.get(cache_key)
            if cached_id:
                try:
                    booking = self._fetch_booking(cached_id)
                    return Response(
                        BookingDetailSerializer(
                            booking, context={'request': request},
                        ).data,
                        status=status.HTTP_200_OK,
                    )
                except Booking.DoesNotExist:
                    pass

        customer = self._resolve_customer(request, data)
        items_data = data.pop('items')
        parties_data = data.pop('parties', [])
        data.pop('customer_code', None)

        try:
            booking = BookingService.create_booking_from_data(
                data=data,
                items_data=items_data,
                customer=customer,
                user=request.user,
                request=request,
                source_channel='API',
                parties_data=parties_data or None,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_400_BAD_REQUEST,
            )

        if idempotency_key:
            cache.set(cache_key, booking.pk, timeout=86400)

        booking = self._fetch_booking(booking.pk)
        return Response(
            BookingDetailSerializer(
                booking, context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    # ─── Update ─────────────────────────────────────────────────

    def partial_update(self, request, pk=None):
        """PATCH /api/v1/bookings/{id}/ — Update a draft booking."""
        booking = self.get_object()

        serializer = BookingUpdateSerializer(
            data=request.data,
            context={'request': request, 'booking': booking},
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        items_data = data.pop('items', None)

        try:
            booking = BookingService.update_booking_from_data(
                booking=booking,
                data=data,
                user=request.user,
                request=request,
                items_data=items_data,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_400_BAD_REQUEST,
            )

        booking = self._fetch_booking(booking.pk)
        return Response(
            BookingDetailSerializer(
                booking, context={'request': request},
            ).data,
        )

    # ─── Status transitions ─────────────────────────────────────

    @action(detail=True, methods=['post'], url_path='submit')
    def submit(self, request, pk=None):
        """POST /api/v1/bookings/{id}/submit/ — Submit a draft booking."""
        booking = self.get_object()
        try:
            BookingService.submit_booking(
                booking, user=request.user, request=request,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_400_BAD_REQUEST,
            )
        booking = self._fetch_booking(booking.pk)
        return Response(
            BookingDetailSerializer(
                booking, context={'request': request},
            ).data,
        )

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel(self, request, pk=None):
        """POST /api/v1/bookings/{id}/cancel/ — Cancel a booking."""
        booking = self.get_object()
        reason = request.data.get('reason', '')
        try:
            BookingService.cancel_booking(
                booking, user=request.user, reason=reason, request=request,
            )
        except ValueError as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_400_BAD_REQUEST,
            )
        booking = self._fetch_booking(booking.pk)
        return Response(
            BookingDetailSerializer(
                booking, context={'request': request},
            ).data,
        )

    # ─── Documents ──────────────────────────────────────────────

    @action(detail=True, methods=['get', 'post'], url_path='documents',
            parser_classes=[MultiPartParser, FormParser])
    def documents(self, request, pk=None):
        """
        GET  — List documents for a booking.
        POST — Upload a document to a booking.
        """
        booking = self.get_object()

        if request.method == 'GET':
            docs = booking.documents.all()
            serializer = BookingDocumentListSerializer(
                docs, many=True, context={'request': request},
            )
            return Response(serializer.data)

        # POST — upload
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data['file']
        doc_type = serializer.validated_data['document_type']
        notes = serializer.validated_data.get('notes', '')

        if booking.status in ('CANCELLED', 'COMPLETED', 'REJECTED'):
            return Response(
                {'error': 'Cannot upload documents to a closed booking.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            document = BookingDocument(
                booking=booking,
                document_type=doc_type,
                file=uploaded_file,
                uploaded_by=request.user,
                original_filename=uploaded_file.name,
                file_size=uploaded_file.size,
                notes=notes,
            )
            document.save()

            BookingService._log(
                booking, 'DOCUMENT_UPLOADED', user=request.user,
                request=request,
                new_value={
                    'document_type': doc_type,
                    'filename': uploaded_file.name,
                    'size': uploaded_file.size,
                },
            )

        return Response(
            BookingDocumentListSerializer(
                document, context={'request': request},
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=['get'],
        url_path='documents/(?P<doc_id>[0-9]+)/download',
    )
    def download(self, request, pk=None, doc_id=None):
        """Download a specific document."""
        booking = self.get_object()
        document = get_object_or_404(
            BookingDocument, id=doc_id, booking=booking,
        )
        return FileResponse(
            document.file.open('rb'),
            as_attachment=True,
            filename=document.original_filename,
        )

    # ─── FMS / Carrier callbacks ────────────────────────────────

    @action(detail=True, methods=['post'], url_path='callback',
            permission_classes=[IsAdminUser])
    def callback(self, request, pk=None):
        """FMS callback — receives reference numbers from external FMS."""
        booking = self.get_object()

        serializer = FMSCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        updated_fields = []
        for field in ['fms_shipment_id', 'hbl_number', 'mbl_number',
                      'hawb_number', 'mawb_number']:
            value = data.get(field, '')
            if value:
                setattr(booking, field, value)
                updated_fields.append(field)

        booking.fms_push_status = 'CALLBACK_RECEIVED'
        updated_fields.append('fms_push_status')
        booking.save(update_fields=updated_fields + ['updated_at'])

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
            booking.booking_number, data,
        )

        return Response(
            {'status': 'ok', 'booking_number': booking.booking_number},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='carrier-callback',
            permission_classes=[IsAdminUser])
    def carrier_callback(self, request, pk=None):
        """Carrier callback — receives booking confirmation/rejection."""
        booking = self.get_object()

        if booking.status in ('CANCELLED', 'COMPLETED'):
            return Response(
                {'error': f'Booking is {booking.status} — callback rejected.'},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = CarrierCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from integrations.carrier_dispatch import process_carrier_callback
        process_carrier_callback(booking, serializer.validated_data)

        logger.info(
            'Carrier callback received for %s: status=%s',
            booking.booking_number, request.data.get('status', 'unknown'),
        )

        return Response(
            {'status': 'ok', 'booking_number': booking.booking_number},
            status=status.HTTP_200_OK,
        )

    # ─── Helpers ────────────────────────────────────────────────

    def _resolve_customer(self, request, data):
        """Determine which customer the booking belongs to."""
        user = request.user
        if user.is_staff:
            customer_code = data.get('customer_code')
            if customer_code:
                try:
                    return Customer.objects.get(
                        code=customer_code, is_active=True,
                    )
                except Customer.DoesNotExist:
                    raise ValidationError(
                        {'customer_code': f'Customer "{customer_code}" not found.'},
                    )
            raise ValidationError(
                {'customer_code': 'Staff must specify customer_code.'},
            )

        profile = getattr(user, 'profile', None)
        if profile and profile.customer:
            return profile.customer

        raise ValidationError(
            {'detail': 'Your account has no customer profile.'},
        )

    def _fetch_booking(self, pk):
        """Re-fetch booking with all relations for serialization."""
        return Booking.objects.select_related(
            'customer', 'origin_port', 'destination_port',
            'container_type', 'carrier_config',
        ).prefetch_related(
            'items', 'booking_parties', 'documents',
        ).get(pk=pk)
