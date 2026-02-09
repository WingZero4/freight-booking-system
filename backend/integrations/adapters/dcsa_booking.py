"""
DCSA Booking API v2 adapter stub.

Implements the Digital Container Shipping Association (DCSA) standard
for ocean carrier booking requests. DCSA defines the API contract;
individual carriers (Maersk, MSC, Hapag-Lloyd, CMA CGM) expose
DCSA-compliant endpoints.

This is a stub — full implementation requires carrier-specific
API credentials and access to a test environment.
"""
import logging

from .base import BaseCarrierAdapter, AdapterResult

logger = logging.getLogger(__name__)


class DCSABookingAdapter(BaseCarrierAdapter):
    """
    DCSA Booking API v2 adapter.

    Maps canonical booking data to DCSA JSON schema:
    - POST /v2/bookings (create booking)
    - PUT /v2/bookings/{ref} (amend booking)
    - PATCH /v2/bookings/{ref} (cancel booking)

    Carrier callbacks arrive at our callback endpoint with DCSA
    event structure (bookingNotification).
    """

    def _build_dcsa_payload(self, booking_data):
        """Transform canonical booking dict to DCSA Booking request schema."""
        route = booking_data.get('route', {})
        container = booking_data.get('container', {})
        cargo = booking_data.get('cargo', {})

        return {
            'receiptTypeAtOrigin': 'CY',
            'deliveryTypeAtDestination': 'CY',
            'cargoMovementTypeAtOrigin': 'FCL',
            'cargoMovementTypeAtDestination': 'FCL',
            'isPartialLoadAllowed': False,
            'expectedDepartureDate': str(
                route.get('etd') or route.get('cargo_ready_date', '')
            ),
            'transportDocumentTypeCode': 'BOL',
            'isExportDeclarationRequired': False,
            'isImportLicenseRequired': False,
            'placeOfBLIssue': {
                'UNLocationCode': route.get('origin', {}).get('code', ''),
            },
            'shipmentLocations': [
                {
                    'locationType': 'PRE',
                    'location': {
                        'UNLocationCode': route.get('origin', {}).get('code', ''),
                    },
                },
                {
                    'locationType': 'POD',
                    'location': {
                        'UNLocationCode': route.get('destination', {}).get('code', ''),
                    },
                },
            ],
            'requestedEquipments': [
                {
                    'ISOEquipmentCode': container.get('type_code', '22G1'),
                    'units': container.get('count', 1),
                    'isShipperOwned': False,
                }
            ],
            'commodities': [
                {
                    'commodityType': cargo.get(
                        'commodity_description', 'General Cargo'
                    ),
                    'cargoGrossWeightUnit': 'KGM',
                    'cargoGrossWeight': float(
                        cargo.get('total_weight_kg') or 0
                    ),
                }
            ],
        }

    def submit_booking(self, booking_data):
        logger.info(
            'DCSA booking submission (stub) for %s',
            booking_data.get('booking_number', 'unknown'),
        )
        payload = self._build_dcsa_payload(booking_data)

        return AdapterResult(
            success=False,
            error_message=(
                'DCSA Booking adapter is a stub. '
                'Configure carrier API credentials and endpoint to enable.'
            ),
            response_data={'dcsa_payload_preview': payload},
        )

    def cancel_booking(self, booking_data, carrier_ref):
        return AdapterResult(
            success=False,
            error_message='DCSA booking cancellation not yet implemented.',
        )

    def amend_booking(self, booking_data, carrier_ref):
        return AdapterResult(
            success=False,
            error_message='DCSA booking amendment not yet implemented.',
        )

    def parse_callback(self, payload):
        """Parse DCSA bookingNotification callback into normalized dict."""
        data = payload.get('data', payload)
        status_map = {
            'CONFIRMED': 'CONFIRMED',
            'PENDING_UPDATE': 'AMENDMENT_REQUIRED',
            'REJECTED': 'REJECTED',
            'DECLINED': 'REJECTED',
        }
        booking_status = data.get('bookingStatus', '')
        return {
            'status': status_map.get(booking_status, booking_status),
            'carrier_booking_ref': data.get('carrierBookingReference', ''),
            'vessel_name': data.get('vesselName', ''),
            'voyage_number': data.get('exportVoyageNumber', ''),
            'etd': data.get('expectedDepartureDate', ''),
            'eta': data.get(
                'expectedArrivalAtPlaceOfDeliveryStartDate', ''
            ),
            'container_numbers': [
                eq.get('equipmentReference', '')
                for eq in data.get('confirmedEquipments', [])
                if eq.get('equipmentReference')
            ],
            'message': data.get('reason', ''),
        }
