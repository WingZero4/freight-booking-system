"""
CargoWise eAdaptor adapter — stub for future implementation.

CargoWise uses XML-based Universal Shipment messages (XUS/XUE)
via the eAdaptor API with OAuth2 + certificate authentication.

This adapter requires:
1. CargoWise eAdaptor API credentials from the customer
2. XML schema mapping (canonical JSON → Universal Shipment XML)
3. Customer-specific field mapping (via extra_config)
"""
import logging

from .base import BaseAdapter, AdapterResult

logger = logging.getLogger(__name__)


class CargoWiseAdapter(BaseAdapter):
    """
    CargoWise eAdaptor integration.

    Currently a stub — full implementation requires customer-provided
    API credentials and access to a CargoWise test environment.
    """

    def push_booking(self, canonical_data):
        logger.info(
            'CargoWise push not yet implemented for booking %s',
            canonical_data.get('booking_number', 'unknown')
        )
        return AdapterResult(
            success=False,
            error_message='CargoWise adapter not yet implemented. '
                          'Contact support to configure this integration.',
        )

    def update_milestone(self, canonical_data, milestone_type):
        return AdapterResult(
            success=False,
            error_message='CargoWise milestone updates not yet implemented.',
        )

    def cancel_shipment(self, canonical_data):
        return AdapterResult(
            success=False,
            error_message='CargoWise cancellation not yet implemented.',
        )
