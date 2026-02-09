"""
Base adapter classes for FMS and carrier integrations.

BaseAdapter: FMS adapters (push bookings to customer FMS).
BaseCarrierAdapter: Carrier adapters (submit bookings to shipping lines/airlines).

Both use the canonical booking JSON (from BookingDetailSerializer) as input.
"""
import abc
import logging

logger = logging.getLogger(__name__)


class AdapterResult:
    """Result of an adapter operation."""

    def __init__(self, success, http_status=None, response_data=None,
                 error_message='', references=None):
        self.success = success
        self.http_status = http_status
        self.response_data = response_data
        self.error_message = error_message
        # Dict of reference numbers received back from FMS
        self.references = references or {}


class BaseAdapter(abc.ABC):
    """
    Abstract base class for FMS adapters.

    Each adapter translates the canonical booking JSON into the
    FMS-specific format and handles communication with the FMS API.
    """

    def __init__(self, config):
        """
        Args:
            config: IntegrationConfig instance with connection details.
        """
        self.config = config
        self.endpoint = config.api_endpoint
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.auth_type = config.auth_type
        self.extra_config = config.extra_config or {}

    def get_auth_headers(self):
        """Build authentication headers based on auth_type."""
        if self.auth_type == 'token':
            return {'Authorization': f'Bearer {self.api_key}'}
        elif self.auth_type == 'basic':
            import base64
            credentials = base64.b64encode(
                f'{self.api_key}:{self.api_secret}'.encode()
            ).decode()
            return {'Authorization': f'Basic {credentials}'}
        return {}

    @abc.abstractmethod
    def push_booking(self, canonical_data):
        """
        Push a confirmed booking to the FMS to create a shipment.

        Args:
            canonical_data: Dict from BookingDetailSerializer.

        Returns:
            AdapterResult with success/failure and any reference numbers.
        """

    @abc.abstractmethod
    def update_milestone(self, canonical_data, milestone_type):
        """
        Send a milestone update (departure, arrival) to the FMS.

        Args:
            canonical_data: Dict from BookingDetailSerializer.
            milestone_type: One of 'IN_TRANSIT', 'COMPLETED'.

        Returns:
            AdapterResult.
        """

    @abc.abstractmethod
    def cancel_shipment(self, canonical_data):
        """
        Notify the FMS that a booking/shipment has been cancelled.

        Args:
            canonical_data: Dict from BookingDetailSerializer.

        Returns:
            AdapterResult.
        """


class BaseCarrierAdapter(abc.ABC):
    """
    Abstract base class for carrier API adapters.

    Carrier adapters translate booking data into carrier-specific
    API formats (DCSA, ONE Record, proprietary) and handle
    booking requests, amendments, and cancellations with carriers.
    """

    def __init__(self, carrier_config):
        self.carrier_config = carrier_config
        self.endpoint = carrier_config.api_endpoint
        self.api_key = carrier_config.api_key
        self.api_secret = carrier_config.api_secret
        self.auth_type = carrier_config.auth_type
        self.extra_config = carrier_config.extra_config or {}

    def get_auth_headers(self):
        """Build authentication headers based on auth_type."""
        if self.auth_type == 'token':
            return {'Authorization': f'Bearer {self.api_key}'}
        elif self.auth_type == 'basic':
            import base64
            credentials = base64.b64encode(
                f'{self.api_key}:{self.api_secret}'.encode()
            ).decode()
            return {'Authorization': f'Basic {credentials}'}
        return {}

    @abc.abstractmethod
    def submit_booking(self, booking_data):
        """
        Submit a new booking request to the carrier.

        Args:
            booking_data: Dict from BookingDetailSerializer.

        Returns:
            AdapterResult with success/failure and references dict.
        """

    @abc.abstractmethod
    def cancel_booking(self, booking_data, carrier_ref):
        """
        Cancel a previously submitted booking with the carrier.

        Args:
            booking_data: Dict from BookingDetailSerializer.
            carrier_ref: Carrier-side booking reference.

        Returns:
            AdapterResult.
        """

    @abc.abstractmethod
    def amend_booking(self, booking_data, carrier_ref):
        """
        Request an amendment to a carrier booking.

        Args:
            booking_data: Updated booking data.
            carrier_ref: Carrier-side booking reference.

        Returns:
            AdapterResult.
        """

    def parse_callback(self, payload):
        """
        Parse a carrier callback payload into a normalized dict.

        Returns dict with keys: status, carrier_booking_ref,
        vessel_name, voyage_number, etd, eta, container_numbers, message.
        Default returns the payload unchanged.
        """
        return payload
