"""Serializers for webhook subscription management."""
from rest_framework import serializers
from .models import WebhookSubscription


VALID_EVENTS = {choice[0] for choice in WebhookSubscription.EVENT_CHOICES}


class WebhookSubscriptionSerializer(serializers.ModelSerializer):
    customer_code = serializers.CharField(
        source='customer.code', read_only=True,
    )

    class Meta:
        model = WebhookSubscription
        fields = [
            'id', 'customer_code', 'url', 'events', 'is_active',
            'created_at', 'updated_at',
            'last_delivery_at', 'consecutive_failures',
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at',
            'last_delivery_at', 'consecutive_failures',
        ]

    def validate_url(self, value):
        if not value.startswith('https://'):
            raise serializers.ValidationError(
                'Webhook URL must use HTTPS.',
            )
        return value

    def validate_events(self, value):
        if not isinstance(value, list) or not value:
            raise serializers.ValidationError(
                'At least one event type is required.',
            )
        invalid = set(value) - VALID_EVENTS
        if invalid:
            raise serializers.ValidationError(
                f'Invalid event types: {", ".join(sorted(invalid))}. '
                f'Valid: {", ".join(sorted(VALID_EVENTS))}',
            )
        return value


class WebhookCreateSerializer(WebhookSubscriptionSerializer):
    """Includes secret field (write-only) for creation."""
    secret = serializers.CharField(
        max_length=200, min_length=16,
        write_only=True,
        help_text='Shared secret for HMAC signatures (min 16 chars)',
    )

    class Meta(WebhookSubscriptionSerializer.Meta):
        fields = WebhookSubscriptionSerializer.Meta.fields + ['secret']
