"""
Maersk API adapter for ocean carrier booking integration.

Implements OAuth 2.0 client credentials flow for authentication and
maps canonical booking data to Maersk's DCSA-inspired API format.

Configuration (via CarrierConfig in Django admin):
    carrier_code: MAEU
    adapter_type: maersk
    api_endpoint: https://api.maersk.com
    auth_type: oauth2
    api_key: {consumer_key from developer.maersk.com}
    api_secret: {client_secret from developer.maersk.com}
    extra_config: {
        "token_url": "https://api.maersk.com/customer-identity/oauth/v2/access_token",
        "brand_scac": "MAEU",
        "booking_path": "/v1/bookings",
        "tracking_path": "/v1/trackings"
    }
"""
import logging
import time
from urllib.parse import quote, urlparse

from django.core.cache import cache as django_cache

import requests

from .base import BaseCarrierAdapter, AdapterResult

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30
TOKEN_REFRESH_MARGIN = 60  # Refresh token 60 seconds before expiry

# Default Maersk endpoints
DEFAULT_TOKEN_URL = (
    'https://api.maersk.com/customer-identity/oauth/v2/access_token'
)
DEFAULT_BOOKING_PATH = '/v1/bookings'
DEFAULT_TRACKING_PATH = '/v1/trackings'

# Allowed Maersk API hosts (prevents SSRF via admin-configurable URLs)
ALLOWED_MAERSK_HOSTS = {'api.maersk.com', 'api-gw.maersk.com'}


class MaerskAdapter(BaseCarrierAdapter):
    """
    Maersk API adapter for booking submission, tracking, and management.

    Uses OAuth 2.0 client credentials flow with Consumer-Key header.
    Token is cached and refreshed automatically before expiry.
    """

    # Token cache uses Django's file-based cache for cross-process sharing

    def __init__(self, carrier_config):
        super().__init__(carrier_config)

        # Extract Maersk-specific config
        self._token_url = self.extra_config.get(
            'token_url', DEFAULT_TOKEN_URL
        )
        self._booking_path = self.extra_config.get(
            'booking_path', DEFAULT_BOOKING_PATH
        )
        self._tracking_path = self.extra_config.get(
            'tracking_path', DEFAULT_TRACKING_PATH
        )
        self._brand_scac = self.extra_config.get('brand_scac', 'MAEU')

        # Validate URLs against allowlist to prevent SSRF
        self._validate_url(self._token_url, 'token_url')
        self._validate_url(self.endpoint, 'api_endpoint')

    @staticmethod
    def _validate_url(url, label):
        """Validate URL uses HTTPS and belongs to allowed Maersk domains."""
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            raise ValueError(f'Maersk {label} must use HTTPS: {url}')
        if parsed.hostname not in ALLOWED_MAERSK_HOSTS:
            raise ValueError(
                f'Maersk {label} host not in allowlist: {parsed.hostname}'
            )

    # ── OAuth 2.0 Token Management ──────────────────────────────────

    def _get_access_token(self):
        """Obtain or refresh OAuth 2.0 access token via Django cache.

        Uses file-based cache for cross-process sharing under WSGI.
        """
        cache_key = f'maersk_oauth:{self.api_key[:8]}'

        # Fast path: check Django cache
        cached_token = django_cache.get(cache_key)
        if cached_token:
            return cached_token

        # Fetch token (may take up to TIMEOUT_SECONDS)
        token, expires_in = self._fetch_oauth_token()

        # Store with TTL (subtract margin so we refresh before actual expiry)
        timeout = max(expires_in - TOKEN_REFRESH_MARGIN, 60)
        django_cache.set(cache_key, token, timeout=timeout)
        logger.info('Maersk OAuth token acquired, expires in %ds', expires_in)
        return token

    def _fetch_oauth_token(self):
        """Make the HTTP request to obtain an OAuth token. Returns (token, expires_in)."""
        headers = {
            'Consumer-Key': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cache-Control': 'no-cache',
        }
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.api_key,
            'client_secret': self.api_secret,
        }

        try:
            response = requests.post(
                self._token_url,
                headers=headers,
                data=data,
                timeout=TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            token_data = response.json()

            token = token_data.get('access_token')
            if not token:
                raise requests.RequestException(
                    f'Maersk OAuth response missing access_token: '
                    f'{list(token_data.keys())}'
                )
            expires_in = int(token_data.get('expires_in', 3600))
            return token, expires_in

        except requests.RequestException as e:
            logger.error(
                'Maersk OAuth token request failed: %s (status=%s)',
                type(e).__name__,
                getattr(getattr(e, 'response', None), 'status_code', 'N/A'),
            )
            raise

    def _get_headers(self):
        """Build authenticated headers for Maersk API calls."""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Consumer-Key': self.api_key,
            'Content-Type': 'application/json',
        }

    # ── Booking Payload Builder ─────────────────────────────────────

    def _build_booking_payload(self, booking_data):
        """Map canonical booking data to Maersk DCSA-inspired format."""
        route = booking_data.get('route') or {}
        container = booking_data.get('container') or {}
        cargo = booking_data.get('cargo') or {}
        parties_raw = booking_data.get('parties', {})
        parties = (
            list(parties_raw.values()) if isinstance(parties_raw, dict)
            else parties_raw
        )

        origin_code = route.get('origin', {}).get('code', '')
        dest_code = route.get('destination', {}).get('code', '')

        payload = {
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
                'UNLocationCode': origin_code,
            },
            'shipmentLocations': [
                {
                    'locationType': 'PRE',
                    'location': {'UNLocationCode': origin_code},
                },
                {
                    'locationType': 'POD',
                    'location': {'UNLocationCode': dest_code},
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

        # Add volume if available
        total_volume = cargo.get('total_volume_cbm')
        if total_volume:
            payload['commodities'][0]['cargoGrossVolumeUnit'] = 'MTQ'
            payload['commodities'][0]['cargoGrossVolume'] = float(total_volume)

        # Add parties (shipper, consignee, notify)
        party_role_map = {
            'SHIPPER': 'OS',    # Original Shipper
            'CONSIGNEE': 'CN',  # Consignee
            'NOTIFY': 'N1',     # Notify Party
        }
        document_parties = []
        for party in parties:
            dcsa_role = party_role_map.get(party.get('role'))
            if not dcsa_role:
                continue
            party_entry = {
                'partyFunction': dcsa_role,
                'party': {
                    'partyName': party.get('company_name', ''),
                    'address': {
                        'street': party.get('address_text', ''),
                    },
                },
            }
            contact_details = []
            if party.get('contact_name'):
                contact_details.append({
                    'name': party['contact_name'],
                    'email': party.get('email', ''),
                    'phone': party.get('phone', ''),
                })
            if contact_details:
                party_entry['party']['partyContactDetails'] = contact_details
            document_parties.append(party_entry)

        if document_parties:
            payload['documentParties'] = document_parties

        # Add service contract if configured
        contract = self.extra_config.get('contract_number', '')
        if contract:
            payload['serviceContractReference'] = contract

        # Add cargo items with HS codes if available
        items = cargo.get('items', [])
        if items:
            hs_codes = [
                item.get('hs_code')
                for item in items
                if item.get('hs_code')
            ]
            if hs_codes:
                payload['commodities'][0]['HSCodes'] = hs_codes

        # Add hazardous flag
        if cargo.get('is_hazardous'):
            payload['isAMSACIFilingRequired'] = True

        return payload

    # ── Core Adapter Methods ────────────────────────────────────────

    def submit_booking(self, booking_data):
        """Submit a new booking request to Maersk."""
        booking_number = booking_data.get('booking_number', 'unknown')
        logger.info('Submitting booking %s to Maersk', booking_number)

        try:
            payload = self._build_booking_payload(booking_data)
        except Exception as e:
            logger.exception('Maersk payload build error for %s', booking_number)
            return AdapterResult(
                success=False,
                error_message=f'Payload build error: {e}',
            )

        url = f'{self.endpoint}{self._booking_path}'

        try:
            headers = self._get_headers()
        except requests.RequestException as e:
            logger.error('Maersk OAuth failed for %s: %s', booking_number, e)
            return AdapterResult(
                success=False,
                error_message='Carrier authentication failed. Check API credentials.',
            )

        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            resp_data = {}
            references = {}
            try:
                resp_data = response.json()
            except (ValueError, TypeError):
                resp_data = {'raw': response.text[:1000]}

            if response.status_code in (200, 201, 202):
                # Extract references from Maersk response
                ref = (
                    resp_data.get('carrierBookingReference')
                    or resp_data.get('bookingReference', '')
                )
                if ref:
                    references['carrier_booking_ref'] = ref

                for field in (
                    'vesselName', 'vessel_name',
                    'exportVoyageNumber', 'voyage_number',
                ):
                    val = resp_data.get(field)
                    if val:
                        key = (
                            'vessel_name'
                            if 'vessel' in field.lower()
                            else 'voyage_number'
                        )
                        references.setdefault(key, val)

                etd = resp_data.get(
                    'expectedDepartureDate',
                    resp_data.get('etd', ''),
                )
                eta = resp_data.get(
                    'expectedArrivalAtPlaceOfDeliveryStartDate',
                    resp_data.get('eta', ''),
                )
                if etd:
                    references['etd'] = etd
                if eta:
                    references['eta'] = eta

                containers = [
                    eq.get('equipmentReference', '')
                    for eq in resp_data.get('confirmedEquipments', [])
                    if eq.get('equipmentReference')
                ]
                if containers:
                    references['container_numbers'] = containers

                logger.info(
                    'Maersk booking %s submitted successfully, ref: %s',
                    booking_number, references.get('carrier_booking_ref', ''),
                )

                return AdapterResult(
                    success=True,
                    http_status=response.status_code,
                    response_data=resp_data,
                    references=references,
                )

            # Non-success status
            error_msg = resp_data.get(
                'message',
                resp_data.get('errorMessage', f'HTTP {response.status_code}'),
            )
            logger.warning(
                'Maersk booking %s rejected: %s (HTTP %d)',
                booking_number, error_msg, response.status_code,
            )
            return AdapterResult(
                success=False,
                http_status=response.status_code,
                response_data=resp_data,
                error_message=error_msg,
            )

        except requests.Timeout:
            logger.warning('Maersk API timeout for booking %s', booking_number)
            return AdapterResult(
                success=False,
                error_message=f'Carrier API timeout after {TIMEOUT_SECONDS}s.',
            )
        except requests.ConnectionError as e:
            logger.warning('Maersk API connection error: %s', e)
            return AdapterResult(
                success=False,
                error_message='Connection to carrier API failed. Check network configuration.',
            )
        except requests.RequestException as e:
            logger.exception('Maersk API request failed for %s', booking_number)
            return AdapterResult(
                success=False,
                error_message='Carrier API request failed unexpectedly.',
            )

    def cancel_booking(self, booking_data, carrier_ref):
        """Cancel a previously submitted booking with Maersk."""
        if not carrier_ref:
            return AdapterResult(
                success=False,
                error_message='No carrier booking reference to cancel.',
            )

        url = f'{self.endpoint}{self._booking_path}/{quote(carrier_ref, safe="")}'
        logger.info('Cancelling Maersk booking %s', carrier_ref)

        try:
            headers = self._get_headers()
        except requests.RequestException as e:
            logger.error('Maersk OAuth failed for cancel %s: %s', carrier_ref, e)
            return AdapterResult(
                success=False,
                error_message='Carrier authentication failed. Check API credentials.',
            )

        try:
            response = requests.patch(
                url,
                json={
                    'bookingStatus': 'CANCELLED',
                    'reason': 'Cancelled by shipper',
                },
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            success = response.status_code in (200, 204)
            resp_data = {}
            try:
                resp_data = response.json()
            except (ValueError, TypeError):
                resp_data = {'raw': response.text[:500]}

            return AdapterResult(
                success=success,
                http_status=response.status_code,
                response_data=resp_data,
                error_message='' if success else f'HTTP {response.status_code}',
            )

        except requests.RequestException as e:
            logger.exception('Maersk cancel failed for %s', carrier_ref)
            return AdapterResult(
                success=False,
                error_message='Carrier cancellation request failed unexpectedly.',
            )

    def amend_booking(self, booking_data, carrier_ref):
        """Amend a previously submitted booking with Maersk."""
        if not carrier_ref:
            return AdapterResult(
                success=False,
                error_message='No carrier booking reference to amend.',
            )

        url = f'{self.endpoint}{self._booking_path}/{quote(carrier_ref, safe="")}'
        try:
            payload = self._build_booking_payload(booking_data)
        except Exception as e:
            logger.exception('Maersk amend payload build error for %s', carrier_ref)
            return AdapterResult(
                success=False,
                error_message=f'Payload build error: {e}',
            )
        logger.info('Amending Maersk booking %s', carrier_ref)

        try:
            headers = self._get_headers()
        except requests.RequestException as e:
            logger.error('Maersk OAuth failed for amend %s: %s', carrier_ref, e)
            return AdapterResult(
                success=False,
                error_message='Carrier authentication failed. Check API credentials.',
            )

        try:
            response = requests.put(
                url,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            success = response.status_code in (200, 202)
            resp_data = {}
            try:
                resp_data = response.json()
            except (ValueError, TypeError):
                resp_data = {'raw': response.text[:500]}

            return AdapterResult(
                success=success,
                http_status=response.status_code,
                response_data=resp_data,
                error_message='' if success else f'HTTP {response.status_code}',
            )

        except requests.RequestException as e:
            logger.exception('Maersk amend failed for %s', carrier_ref)
            return AdapterResult(
                success=False,
                error_message='Carrier amendment request failed unexpectedly.',
            )

    # ── Tracking (bonus utility) ────────────────────────────────────

    def get_tracking(self, tracking_number):
        """
        Track a shipment by booking number, B/L, or container number.

        Not part of BaseCarrierAdapter — callable directly for
        ops dashboard or tracking views.

        Returns:
            AdapterResult with tracking events in response_data.
        """
        url = f'{self.endpoint}{self._tracking_path}/{quote(tracking_number, safe="")}'
        logger.info('Tracking Maersk shipment %s', tracking_number)

        try:
            headers = self._get_headers()
        except requests.RequestException as e:
            logger.error('Maersk OAuth failed for tracking %s: %s', tracking_number, e)
            return AdapterResult(
                success=False,
                error_message='Carrier authentication failed. Check API credentials.',
            )

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            resp_data = {}
            try:
                resp_data = response.json()
            except (ValueError, TypeError):
                resp_data = {'raw': response.text[:1000]}

            success = response.status_code == 200
            return AdapterResult(
                success=success,
                http_status=response.status_code,
                response_data=resp_data,
                error_message='' if success else f'HTTP {response.status_code}',
            )

        except requests.RequestException as e:
            logger.exception('Maersk tracking failed for %s', tracking_number)
            return AdapterResult(
                success=False,
                error_message='Carrier tracking request failed unexpectedly.',
            )

    # ── Callback Parser ─────────────────────────────────────────────

    def parse_callback(self, payload):
        """
        Parse a Maersk callback/webhook into normalized format.

        Maersk follows DCSA event structure. This normalizes into
        our standard dict format expected by carrier_dispatch.py.
        """
        data = payload.get('data', payload)

        status_map = {
            'CONFIRMED': 'CONFIRMED',
            'PENDING_UPDATE': 'AMENDMENT_REQUIRED',
            'REJECTED': 'REJECTED',
            'DECLINED': 'REJECTED',
            'CANCELLED': 'CANCELLED',
        }
        booking_status = (
            data.get('bookingStatus')
            or data.get('status', '')
        )

        containers = [
            eq.get('equipmentReference', '')
            for eq in data.get('confirmedEquipments', [])
            if eq.get('equipmentReference')
        ]

        return {
            'status': status_map.get(booking_status, booking_status),
            'carrier_booking_ref': (
                data.get('carrierBookingReference')
                or data.get('carrier_booking_ref', '')
            ),
            'vessel_name': (
                data.get('vesselName')
                or data.get('vessel_name', '')
            ),
            'voyage_number': (
                data.get('exportVoyageNumber')
                or data.get('voyage_number', '')
            ),
            'etd': (
                data.get('expectedDepartureDate')
                or data.get('etd', '')
            ),
            'eta': (
                data.get('expectedArrivalAtPlaceOfDeliveryStartDate')
                or data.get('eta', '')
            ),
            'container_numbers': containers,
            'message': data.get('reason', data.get('message', '')),
        }
