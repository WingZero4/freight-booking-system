"""
DRF serializers for the freight booking system.

BookingSerializer produces the canonical JSON format used by FMS adapters.
"""
from decimal import Decimal

from rest_framework import serializers
from . import validators
from .models import (
    Booking, BookingItem, BookingDocument, BookingParty,
    Customer, Port, ContainerType,
)


class PortSerializer(serializers.ModelSerializer):
    class Meta:
        model = Port
        fields = ['code', 'name', 'country']


class ContainerTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContainerType
        fields = ['code', 'name', 'size_ft']


class BookingItemSerializer(serializers.ModelSerializer):
    dimensions = serializers.SerializerMethodField()
    hazmat = serializers.SerializerMethodField()

    class Meta:
        model = BookingItem
        fields = [
            'id', 'description', 'hs_code', 'package_type', 'quantity',
            'weight_kg', 'volume_cbm', 'dimensions',
            'marks_and_numbers', 'country_of_origin', 'hazmat',
        ]

    def get_dimensions(self, obj):
        if obj.length_cm and obj.width_cm and obj.height_cm:
            return {
                'length_cm': float(obj.length_cm),
                'width_cm': float(obj.width_cm),
                'height_cm': float(obj.height_cm),
            }
        return None

    def get_hazmat(self, obj):
        if obj.is_hazardous:
            return {
                'un_number': obj.un_number,
                'imo_class': obj.imo_class,
            }
        return None


class BookingPartySerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingParty
        fields = [
            'role', 'company_name', 'contact_name',
            'address_text', 'email', 'phone', 'tax_id',
        ]


class BookingDocumentListSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = BookingDocument
        fields = [
            'id', 'document_type', 'original_filename',
            'file_size', 'uploaded_at', 'download_url',
        ]

    def get_download_url(self, obj):
        request = self.context.get('request')
        url = f'/api/v1/bookings/{obj.booking_id}/documents/{obj.id}/download/'
        if request:
            return request.build_absolute_uri(url)
        return url


class BookingListSerializer(serializers.ModelSerializer):
    """Compact serializer for list views."""
    customer_code = serializers.CharField(source='customer.code', read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    origin = serializers.CharField(source='origin_port.code', read_only=True)
    destination = serializers.CharField(source='destination_port.code', read_only=True)
    container = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_number', 'status', 'transport_mode',
            'customer_code', 'customer_name',
            'origin', 'destination',
            'container', 'container_count',
            'cargo_ready_date', 'etd', 'eta',
            'total_weight_kg', 'total_volume_cbm',
            'fms_push_status',
            'created_at', 'updated_at',
        ]

    def get_container(self, obj):
        if obj.container_type:
            return obj.container_type.code
        return None


class BookingDetailSerializer(serializers.ModelSerializer):
    """Full canonical serializer for detail view and FMS integration."""

    # Nested objects
    route = serializers.SerializerMethodField()
    carrier = serializers.SerializerMethodField()
    container = serializers.SerializerMethodField()
    cargo = serializers.SerializerMethodField()
    parties = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    references = serializers.SerializerMethodField()
    timestamps = serializers.SerializerMethodField()
    fms = serializers.SerializerMethodField()
    carrier_integration = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_number', 'status', 'transport_mode',
            'incoterms', 'incoterms_location',
            'chargeable_weight_kg', 'flight_number',
            'route', 'carrier', 'container', 'cargo',
            'parties', 'documents', 'references', 'timestamps',
            'fms', 'carrier_integration',
        ]

    def get_route(self, obj):
        return {
            'origin': PortSerializer(obj.origin_port).data,
            'destination': PortSerializer(obj.destination_port).data,
            'etd': obj.etd,
            'eta': obj.eta,
            'cargo_ready_date': obj.cargo_ready_date,
            'cargo_cutoff_date': obj.cargo_cutoff_date,
        }

    def get_carrier(self, obj):
        return {
            'name': obj.carrier_name,
            'booking_ref': obj.carrier_booking_ref,
            'vessel': obj.vessel_name,
            'voyage': obj.voyage_number,
        }

    def get_container(self, obj):
        if obj.container_type:
            return {
                'type_code': obj.container_type.code,
                'type_name': obj.container_type.name,
                'count': obj.container_count,
            }
        return None

    def get_cargo(self, obj):
        items = obj.items.all()
        return {
            'commodity_description': obj.commodity_description,
            'is_hazardous': obj.is_hazardous,
            'total_weight_kg': obj.total_weight_kg,
            'total_volume_cbm': obj.total_volume_cbm,
            'items': BookingItemSerializer(items, many=True).data,
        }

    def get_parties(self, obj):
        result = {}
        for bp in obj.booking_parties.all():
            key = bp.role.lower()
            result[key] = BookingPartySerializer(bp).data
        return result

    def get_documents(self, obj):
        docs = obj.documents.all()
        return BookingDocumentListSerializer(
            docs, many=True, context=self.context
        ).data

    def get_references(self, obj):
        return {
            'external_reference': obj.external_reference,
            'customer_code': obj.customer.code,
            'special_instructions': obj.special_instructions,
        }

    def get_timestamps(self, obj):
        return {
            'created_at': obj.created_at,
            'submitted_at': obj.submitted_at,
            'confirmed_at': obj.confirmed_at,
            'in_transit_at': obj.in_transit_at,
            'completed_at': obj.completed_at,
            'cancelled_at': obj.cancelled_at,
        }

    def get_fms(self, obj):
        request = self.context.get('request')
        is_staff = request and request.user and request.user.is_staff
        result = {
            'shipment_id': obj.fms_shipment_id,
            'hbl_number': obj.hbl_number,
            'mbl_number': obj.mbl_number,
            'hawb_number': obj.hawb_number,
            'mawb_number': obj.mawb_number,
            'push_status': obj.fms_push_status,
        }
        if is_staff:
            result['push_error'] = obj.fms_push_error
        return result

    def get_carrier_integration(self, obj):
        carrier_config = getattr(obj, 'carrier_config', None)
        request = self.context.get('request')
        is_staff = request and request.user and request.user.is_staff
        result = {
            'request_status': obj.carrier_request_status,
            'confirmation_ref': obj.carrier_confirmation_ref,
            'container_numbers': (
                [cn for cn in obj.container_numbers.split('\n') if cn]
                if obj.container_numbers else []
            ),
        }
        # Staff-only fields
        if is_staff:
            result['carrier_config_id'] = obj.carrier_config_id
            result['carrier_config_name'] = (
                carrier_config.carrier_name if carrier_config else None
            )
            result['request_error'] = obj.carrier_request_error
        return result


class FMSCallbackSerializer(serializers.Serializer):
    """Serializer for FMS callback payload (reference numbers flowing back)."""
    fms_shipment_id = serializers.CharField(
        required=False, allow_blank=True, max_length=100)
    hbl_number = serializers.CharField(
        required=False, allow_blank=True, max_length=50)
    mbl_number = serializers.CharField(
        required=False, allow_blank=True, max_length=50)
    hawb_number = serializers.CharField(
        required=False, allow_blank=True, max_length=50)
    mawb_number = serializers.CharField(
        required=False, allow_blank=True, max_length=50)


class CarrierCallbackSerializer(serializers.Serializer):
    """Serializer for carrier callback payload (booking confirmation/rejection)."""
    status = serializers.ChoiceField(
        choices=['CONFIRMED', 'REJECTED', 'AMENDMENT_REQUIRED'],
    )
    carrier_booking_ref = serializers.CharField(
        required=False, allow_blank=True, max_length=100)
    vessel_name = serializers.CharField(
        required=False, allow_blank=True, max_length=100)
    voyage_number = serializers.CharField(
        required=False, allow_blank=True, max_length=50)
    etd = serializers.DateField(required=False, allow_null=True)
    eta = serializers.DateField(required=False, allow_null=True)
    container_numbers = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False, default=list,
    )
    message = serializers.CharField(
        required=False, allow_blank=True, max_length=1000)


# ─── Write serializers (API create/update) ────────────────────────────


class BookingItemWriteSerializer(serializers.Serializer):
    """Writable serializer for cargo items."""
    description = serializers.CharField(max_length=500)
    package_type = serializers.ChoiceField(
        choices=BookingItem.PACKAGE_TYPE_CHOICES, default='PACKAGE',
    )
    quantity = serializers.IntegerField(min_value=1, max_value=99999)
    weight_kg = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=Decimal('0.01'),
    )
    hs_code = serializers.CharField(max_length=10, required=False, default='')
    volume_cbm = serializers.DecimalField(
        max_digits=10, decimal_places=3, required=False, allow_null=True, default=None,
    )
    length_cm = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, default=None,
    )
    width_cm = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, default=None,
    )
    height_cm = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True, default=None,
    )
    marks_and_numbers = serializers.CharField(
        max_length=500, required=False, default='',
    )
    is_hazardous = serializers.BooleanField(required=False, default=False)
    un_number = serializers.CharField(max_length=4, required=False, default='')
    imo_class = serializers.CharField(max_length=10, required=False, default='')
    country_of_origin = serializers.CharField(
        max_length=2, required=False, default='',
    )


class BookingPartyWriteSerializer(serializers.Serializer):
    """Writable serializer for inline party data."""
    role = serializers.ChoiceField(choices=BookingParty.ROLE_CHOICES)
    company_name = serializers.CharField(max_length=255)
    contact_name = serializers.CharField(
        max_length=255, required=False, default='',
    )
    address_text = serializers.CharField(required=False, default='')
    email = serializers.EmailField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(max_length=50, required=False, default='')
    tax_id = serializers.CharField(max_length=50, required=False, default='')


class BookingCreateSerializer(serializers.Serializer):
    """
    Top-level serializer for POST /api/v1/bookings/.

    Ports and container types are specified by code (not PK).
    """
    # Required
    transport_mode = serializers.ChoiceField(
        choices=Booking.TRANSPORT_MODE_CHOICES,
    )
    origin_port = serializers.SlugRelatedField(
        slug_field='code', queryset=Port.objects.filter(is_active=True),
    )
    destination_port = serializers.SlugRelatedField(
        slug_field='code', queryset=Port.objects.filter(is_active=True),
    )
    cargo_ready_date = serializers.DateField()
    incoterms = serializers.ChoiceField(
        choices=Booking.INCOTERMS_CHOICES, default='FOB',
    )

    # Conditionally required (Sea FCL needs container)
    container_type = serializers.SlugRelatedField(
        slug_field='code', queryset=ContainerType.objects.all(),
        required=False, allow_null=True,
    )
    container_count = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=999,
    )

    # Optional
    incoterms_location = serializers.CharField(
        max_length=255, required=False, default='',
    )
    commodity_description = serializers.CharField(
        max_length=500, required=False, default='',
    )
    is_hazardous = serializers.BooleanField(required=False, default=False)
    external_reference = serializers.CharField(
        max_length=100, required=False, default='',
    )
    special_instructions = serializers.CharField(required=False, default='')
    chargeable_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False,
        allow_null=True, default=None,
    )
    flight_number = serializers.CharField(
        max_length=20, required=False, default='',
    )

    # Staff only: specify customer
    customer_code = serializers.CharField(max_length=20, required=False)

    # Nested
    items = BookingItemWriteSerializer(many=True)
    parties = BookingPartyWriteSerializer(many=True, required=False, default=list)

    # Idempotency
    idempotency_key = serializers.CharField(
        max_length=100, required=False,
    )

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError('At least one cargo item is required.')
        return value

    def validate(self, attrs):
        # Cross-field validation
        data = {
            'transport_mode': attrs['transport_mode'],
            'origin_port': attrs['origin_port'].pk,
            'destination_port': attrs['destination_port'].pk,
            'cargo_ready_date': attrs['cargo_ready_date'],
            'container_type': attrs.get('container_type'),
            'container_type_id': (
                attrs['container_type'].pk if attrs.get('container_type') else None
            ),
            'container_count': attrs.get('container_count'),
            'incoterms': attrs.get('incoterms', 'FOB'),
        }
        errors = validators.validate_booking_data(data)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class BookingUpdateSerializer(serializers.Serializer):
    """
    Serializer for PATCH /api/v1/bookings/{id}/.

    All fields optional. Only DRAFT bookings can be updated.
    Items replaced wholesale if provided (not merged).
    """
    transport_mode = serializers.ChoiceField(
        choices=Booking.TRANSPORT_MODE_CHOICES, required=False,
    )
    origin_port = serializers.SlugRelatedField(
        slug_field='code', queryset=Port.objects.filter(is_active=True),
        required=False,
    )
    destination_port = serializers.SlugRelatedField(
        slug_field='code', queryset=Port.objects.filter(is_active=True),
        required=False,
    )
    cargo_ready_date = serializers.DateField(required=False)
    incoterms = serializers.ChoiceField(
        choices=Booking.INCOTERMS_CHOICES, required=False,
    )
    container_type = serializers.SlugRelatedField(
        slug_field='code', queryset=ContainerType.objects.all(),
        required=False, allow_null=True,
    )
    container_count = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=999,
    )
    incoterms_location = serializers.CharField(max_length=255, required=False)
    commodity_description = serializers.CharField(max_length=500, required=False)
    is_hazardous = serializers.BooleanField(required=False)
    external_reference = serializers.CharField(max_length=100, required=False)
    special_instructions = serializers.CharField(required=False)
    chargeable_weight_kg = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
    )
    flight_number = serializers.CharField(max_length=20, required=False)

    # If provided, replaces all existing items
    items = BookingItemWriteSerializer(many=True, required=False)

    def validate_items(self, value):
        if value is not None and len(value) == 0:
            raise serializers.ValidationError(
                'At least one cargo item is required.',
            )
        return value

    def validate(self, attrs):
        booking = self.context.get('booking')
        if not booking:
            raise serializers.ValidationError('Booking context required.')
        if booking.status != 'DRAFT':
            raise serializers.ValidationError(
                'Only draft bookings can be updated.',
            )

        # Merge with existing booking for cross-field validation
        merged = {
            'transport_mode': attrs.get(
                'transport_mode', booking.transport_mode,
            ),
            'origin_port': (
                attrs['origin_port'].pk if 'origin_port' in attrs
                else booking.origin_port_id
            ),
            'destination_port': (
                attrs['destination_port'].pk if 'destination_port' in attrs
                else booking.destination_port_id
            ),
            'cargo_ready_date': attrs.get(
                'cargo_ready_date', booking.cargo_ready_date,
            ),
            'container_type': attrs.get(
                'container_type', booking.container_type,
            ),
            'container_type_id': (
                attrs['container_type'].pk
                if 'container_type' in attrs and attrs['container_type']
                else booking.container_type_id
            ),
            'container_count': attrs.get(
                'container_count', booking.container_count,
            ),
            'incoterms': attrs.get('incoterms', booking.incoterms),
        }
        errors = validators.validate_booking_data(
            merged, is_edit=True, existing_booking=booking,
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class DocumentUploadSerializer(serializers.Serializer):
    """Serializer for POST /api/v1/bookings/{id}/documents/."""
    document_type = serializers.ChoiceField(
        choices=BookingDocument.DOCUMENT_TYPE_CHOICES,
    )
    file = serializers.FileField()
    notes = serializers.CharField(max_length=255, required=False, default='')

    def validate_file(self, value):
        err = validators.validate_file_extension(value.name)
        if err:
            raise serializers.ValidationError(err)
        err = validators.validate_file_size(value.size)
        if err:
            raise serializers.ValidationError(err)
        return value
