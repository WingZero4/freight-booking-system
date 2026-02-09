"""
Models for FMS (Freight Management System) integration.

IntegrationConfig: Per-customer FMS connection settings.
IntegrationLog: Audit trail for every push/callback event.
"""
from django.db import models
from django.utils import timezone


class IntegrationConfig(models.Model):
    """Per-customer FMS integration configuration."""

    ADAPTER_CHOICES = [
        ('webhook', 'Generic Webhook (JSON POST)'),
        ('cargowise', 'CargoWise eAdaptor'),
        ('dcsa', 'DCSA Booking API'),
        ('file_drop', 'File Drop (SFTP/EDI)'),
    ]

    AUTH_TYPE_CHOICES = [
        ('token', 'API Token / Bearer'),
        ('oauth2', 'OAuth 2.0 Client Credentials'),
        ('basic', 'Basic Auth'),
        ('certificate', 'Client Certificate'),
    ]

    customer = models.OneToOneField(
        'bookings.Customer', on_delete=models.CASCADE,
        related_name='integration_config'
    )
    adapter_type = models.CharField(max_length=30, choices=ADAPTER_CHOICES)
    api_endpoint = models.URLField(help_text='FMS API endpoint URL')
    auth_type = models.CharField(
        max_length=20, choices=AUTH_TYPE_CHOICES, default='token'
    )
    api_key = models.CharField(
        max_length=500, blank=True,
        help_text='API key or OAuth client ID'
    )
    api_secret = models.CharField(
        max_length=500, blank=True,
        help_text='API secret or OAuth client secret'
    )
    extra_config = models.JSONField(
        default=dict, blank=True,
        help_text='Additional adapter-specific settings (JSON)'
    )
    auto_push_on_confirm = models.BooleanField(
        default=True,
        help_text='Automatically push to FMS when booking is confirmed'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer.code} → {self.get_adapter_type_display()}"

    class Meta:
        verbose_name = 'FMS integration config'
        verbose_name_plural = 'FMS integration configs'


class IntegrationLog(models.Model):
    """Audit trail for FMS integration events."""

    EVENT_CHOICES = [
        ('PUSH', 'Push to FMS'),
        ('PUSH_SUCCESS', 'Push Successful'),
        ('PUSH_FAILED', 'Push Failed'),
        ('CALLBACK', 'Callback Received'),
        ('UPDATE', 'Milestone Update'),
        ('CANCEL', 'Cancellation Sent'),
        ('RETRY', 'Manual Retry'),
    ]

    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.CASCADE,
        related_name='integration_logs'
    )
    config = models.ForeignKey(
        IntegrationConfig, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    event = models.CharField(max_length=20, choices=EVENT_CHOICES)
    adapter_type = models.CharField(max_length=30, blank=True)
    request_payload = models.JSONField(
        null=True, blank=True,
        help_text='Outbound payload sent to FMS'
    )
    response_payload = models.JSONField(
        null=True, blank=True,
        help_text='Response received from FMS'
    )
    http_status = models.IntegerField(
        null=True, blank=True,
        help_text='HTTP status code of FMS response'
    )
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return (
            f"{self.booking.booking_number} — "
            f"{self.get_event_display()} ({self.created_at:%Y-%m-%d %H:%M})"
        )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'FMS integration log'
        verbose_name_plural = 'FMS integration logs'
