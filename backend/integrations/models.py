"""
Models for integration layer.

IntegrationConfig: Per-customer FMS connection settings.
CarrierConfig: Per-carrier API connection settings.
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


class CarrierConfig(models.Model):
    """Global carrier API configuration (one per shipping line / airline)."""

    CARRIER_TYPE_CHOICES = [
        ('ocean', 'Ocean Carrier'),
        ('air', 'Air Carrier'),
        ('rail', 'Rail Carrier'),
        ('trucking', 'Trucking Carrier'),
    ]

    ADAPTER_CHOICES = [
        ('carrier_webhook', 'Generic Webhook (JSON POST)'),
        ('dcsa', 'DCSA Booking API v2'),
        ('one_record', 'IATA ONE Record'),
    ]

    AUTH_TYPE_CHOICES = [
        ('token', 'API Token / Bearer'),
        ('oauth2', 'OAuth 2.0 Client Credentials'),
        ('basic', 'Basic Auth'),
    ]

    carrier_code = models.CharField(
        max_length=20, unique=True,
        help_text='SCAC code for ocean (e.g. MAEU), IATA code for air (e.g. LH)'
    )
    carrier_name = models.CharField(max_length=100, help_text='Display name e.g. Maersk')
    carrier_type = models.CharField(max_length=20, choices=CARRIER_TYPE_CHOICES)

    adapter_type = models.CharField(max_length=30, choices=ADAPTER_CHOICES)
    api_endpoint = models.URLField(help_text='Carrier API base URL')
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
        help_text='Carrier-specific settings (JSON)'
    )

    supports_async_callback = models.BooleanField(
        default=True,
        help_text='Carrier confirms via async callback (vs synchronous response)'
    )
    auto_chain_to_fms = models.BooleanField(
        default=True,
        help_text='Automatically push to customer FMS after carrier confirms'
    )
    callback_secret = models.CharField(
        max_length=200, blank=True,
        help_text='Shared secret for validating carrier callback signatures'
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.carrier_code} — {self.carrier_name}"

    class Meta:
        verbose_name = 'carrier config'
        verbose_name_plural = 'carrier configs'
        ordering = ['carrier_name']


class IntegrationLog(models.Model):
    """Audit trail for FMS and carrier integration events."""

    EVENT_CHOICES = [
        ('PUSH', 'Push to FMS'),
        ('PUSH_SUCCESS', 'Push Successful'),
        ('PUSH_FAILED', 'Push Failed'),
        ('CALLBACK', 'Callback Received'),
        ('UPDATE', 'Milestone Update'),
        ('CANCEL', 'Cancellation Sent'),
        ('RETRY', 'Manual Retry'),
        ('CARRIER_SUBMIT', 'Carrier Booking Submitted'),
        ('CARRIER_SUCCESS', 'Carrier Submission Accepted'),
        ('CARRIER_FAILED', 'Carrier Submission Failed'),
        ('CARRIER_CALLBACK', 'Carrier Callback Received'),
        ('CARRIER_CONFIRMED', 'Carrier Booking Confirmed'),
        ('CARRIER_REJECTED', 'Carrier Booking Rejected'),
        ('CARRIER_CANCEL', 'Carrier Cancellation Sent'),
    ]

    booking = models.ForeignKey(
        'bookings.Booking', on_delete=models.CASCADE,
        related_name='integration_logs'
    )
    config = models.ForeignKey(
        IntegrationConfig, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    carrier_config = models.ForeignKey(
        CarrierConfig, on_delete=models.SET_NULL,
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
        verbose_name = 'integration log'
        verbose_name_plural = 'integration logs'


class WebhookSubscription(models.Model):
    """Customer webhook subscription for booking events."""

    EVENT_CHOICES = [
        ('booking.created', 'Booking Created'),
        ('booking.submitted', 'Booking Submitted'),
        ('booking.confirmed', 'Booking Confirmed'),
        ('booking.rejected', 'Booking Rejected'),
        ('booking.in_transit', 'Booking In Transit'),
        ('booking.completed', 'Booking Completed'),
        ('booking.cancelled', 'Booking Cancelled'),
    ]

    customer = models.ForeignKey(
        'bookings.Customer', on_delete=models.CASCADE,
        related_name='webhook_subscriptions',
    )
    url = models.URLField(help_text='Webhook delivery URL (HTTPS required)')
    events = models.JSONField(
        default=list,
        help_text='List of event types to subscribe to',
    )
    secret = models.CharField(
        max_length=200,
        help_text='Shared secret for HMAC-SHA256 signature verification',
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Delivery tracking
    last_delivery_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.customer.code} -> {self.url} ({len(self.events)} events)"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'webhook subscription'
        verbose_name_plural = 'webhook subscriptions'


class WebhookDelivery(models.Model):
    """Log of each webhook delivery attempt."""

    subscription = models.ForeignKey(
        WebhookSubscription, on_delete=models.CASCADE,
        related_name='deliveries',
    )
    event_type = models.CharField(max_length=30)
    payload = models.JSONField()

    # Delivery result
    response_status = models.IntegerField(null=True, blank=True)
    response_body = models.TextField(blank=True, max_length=2000)
    error_message = models.TextField(blank=True)
    success = models.BooleanField(default=False)

    attempt_number = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'webhook delivery'
        verbose_name_plural = 'webhook deliveries'
