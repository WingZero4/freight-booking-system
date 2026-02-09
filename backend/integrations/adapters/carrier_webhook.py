"""
Generic carrier webhook adapter — sends booking requests as JSON POST.

Suitable for carriers with simple REST APIs or for testing integrations.
"""
import logging

import requests

from .base import BaseCarrierAdapter, AdapterResult

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class CarrierWebhookAdapter(BaseCarrierAdapter):
    """
    Generic webhook adapter for carrier booking requests.

    Sends canonical booking JSON to a carrier's webhook URL.
    The carrier can respond synchronously with confirmation details
    or send them later via the carrier-callback endpoint.
    """

    def submit_booking(self, booking_data):
        payload = {
            'action': 'booking_request',
            'booking': booking_data,
        }
        return self._send(payload)

    def cancel_booking(self, booking_data, carrier_ref):
        payload = {
            'action': 'booking_cancellation',
            'carrier_booking_ref': carrier_ref,
            'booking': booking_data,
        }
        return self._send(payload)

    def amend_booking(self, booking_data, carrier_ref):
        payload = {
            'action': 'booking_amendment',
            'carrier_booking_ref': carrier_ref,
            'booking': booking_data,
        }
        return self._send(payload)

    def _send(self, payload):
        """Send JSON payload to the configured carrier endpoint."""
        headers = {
            'Content-Type': 'application/json',
            **self.get_auth_headers(),
        }

        extra_headers = self.extra_config.get('headers', {})
        headers.update(extra_headers)

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            references = {}
            resp_data = {}
            if response.status_code in (200, 201, 202):
                try:
                    resp_data = response.json()
                    for key in ['carrier_booking_ref', 'vessel_name',
                                'voyage_number', 'etd', 'eta',
                                'container_numbers']:
                        if resp_data.get(key):
                            references[key] = resp_data[key]
                except (ValueError, KeyError):
                    resp_data = {'raw': response.text[:1000]}
            else:
                resp_data = {'raw': response.text[:1000]}

            success = response.status_code in (200, 201, 202, 204)

            return AdapterResult(
                success=success,
                http_status=response.status_code,
                response_data=resp_data,
                error_message='' if success else f'HTTP {response.status_code}',
                references=references,
            )

        except requests.Timeout:
            logger.warning('Carrier webhook timeout: %s', self.endpoint)
            return AdapterResult(
                success=False,
                error_message=f'Timeout after {TIMEOUT_SECONDS}s',
            )
        except requests.ConnectionError as e:
            logger.warning('Carrier webhook connection error: %s — %s',
                           self.endpoint, e)
            return AdapterResult(
                success=False,
                error_message=f'Connection error: {e}',
            )
        except requests.RequestException as e:
            logger.exception('Carrier webhook request failed: %s', self.endpoint)
            return AdapterResult(
                success=False,
                error_message=str(e),
            )
