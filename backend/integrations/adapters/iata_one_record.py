"""
IATA ONE Record adapter stub for air cargo bookings.

ONE Record is the IATA standard for data sharing in air cargo,
replacing legacy Cargo-IMP/CIMP messaging. Mandatory for IATA
member airlines since January 2026.

This is a stub — full implementation requires carrier enrollment
in ONE Record and access to their API environment.
"""
import logging

from .base import BaseCarrierAdapter, AdapterResult

logger = logging.getLogger(__name__)


class IATAOneRecordAdapter(BaseCarrierAdapter):
    """
    IATA ONE Record adapter for air carrier bookings.

    Maps canonical booking data to ONE Record Logistics Objects:
    - BookingOption → BookingRequest
    - Piece, Shipment, Waybill objects

    Stub only — returns failure with informational message.
    """

    def submit_booking(self, booking_data):
        logger.info(
            'ONE Record booking submission (stub) for %s',
            booking_data.get('booking_number', 'unknown'),
        )
        return AdapterResult(
            success=False,
            error_message=(
                'IATA ONE Record adapter is a stub. '
                'Contact support to configure carrier API access.'
            ),
        )

    def cancel_booking(self, booking_data, carrier_ref):
        return AdapterResult(
            success=False,
            error_message='ONE Record cancellation not yet implemented.',
        )

    def amend_booking(self, booking_data, carrier_ref):
        return AdapterResult(
            success=False,
            error_message='ONE Record amendment not yet implemented.',
        )
