"""
Base adapter class for FMS integrations.

All FMS adapters inherit from BaseAdapter and implement the abstract methods.
The canonical booking JSON (from BookingDetailSerializer) is the input format.
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
