"""
Generic Webhook adapter — sends booking data as JSON POST to any URL.

This is the universal adapter that works with any FMS or system
that can receive webhook/HTTP POST notifications.
"""
import logging

import requests

from .base import BaseAdapter, AdapterResult

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 30


class WebhookAdapter(BaseAdapter):
    """
    Sends canonical booking JSON to a webhook URL.

    The target FMS receives the full booking payload and can
    respond with reference numbers in the JSON response body.
    """

    def push_booking(self, canonical_data):
        payload = {
            'event': 'booking.confirmed',
            'booking': canonical_data,
        }
        return self._send(payload)

    def update_milestone(self, canonical_data, milestone_type):
        payload = {
            'event': f'booking.{milestone_type.lower()}',
            'booking': canonical_data,
        }
        return self._send(payload)

    def cancel_shipment(self, canonical_data):
        payload = {
            'event': 'booking.cancelled',
            'booking': canonical_data,
        }
        return self._send(payload)

    def _send(self, payload):
        """Send JSON payload to the configured webhook endpoint."""
        headers = {
            'Content-Type': 'application/json',
            **self.get_auth_headers(),
        }

        # Allow extra headers from config
        extra_headers = self.extra_config.get('headers', {})
        headers.update(extra_headers)

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=TIMEOUT_SECONDS,
            )

            # Parse response for reference numbers
            references = {}
            if response.status_code in (200, 201, 202):
                try:
                    resp_data = response.json()
                    for key in ['fms_shipment_id', 'hbl_number', 'mbl_number',
                                'hawb_number', 'mawb_number']:
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
            logger.warning('Webhook timeout: %s', self.endpoint)
            return AdapterResult(
                success=False,
                error_message=f'Timeout after {TIMEOUT_SECONDS}s',
            )
        except requests.ConnectionError as e:
            logger.warning('Webhook connection error: %s — %s', self.endpoint, e)
            return AdapterResult(
                success=False,
                error_message=f'Connection error: {e}',
            )
        except requests.RequestException as e:
            logger.exception('Webhook request failed: %s', self.endpoint)
            return AdapterResult(
                success=False,
                error_message=str(e),
            )
