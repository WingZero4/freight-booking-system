"""
DRF serializers for the freight booking system.

BookingSerializer produces the canonical JSON format used by FMS adapters.
"""
from rest_framework import serializers
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
        return {
            'shipment_id': obj.fms_shipment_id,
            'hbl_number': obj.hbl_number,
            'mbl_number': obj.mbl_number,
            'hawb_number': obj.hawb_number,
            'mawb_number': obj.mawb_number,
            'push_status': obj.fms_push_status,
            'push_error': obj.fms_push_error,
        }

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
