"""
Feature flag and field configuration services.

Provides per-organization feature toggles and per-customer field
visibility/requirements. Staff users bypass field config restrictions.
"""
import logging

from django.core.cache import cache

logger = logging.getLogger(__name__)

_FEATURE_CACHE_TTL = 300  # 5 minutes
_FIELD_CACHE_TTL = 300

# All feature flag field names on OrganizationFeatureConfig
FEATURE_FLAGS = [
    'enable_consolidation',
    'enable_import',
    'enable_parties',
    'enable_documents',
    'enable_milestones',
    'enable_customer_approval',
    'enable_carrier_integration',
    'enable_fms_integration',
    'enable_templates',
    'enable_clone',
    'enable_document_review',
    'enable_sanctions_screening',
    'enable_scheduled_reports',
    'enable_booking_comments',
    'enable_sla_tracking',
    'enable_auto_quoting',
    'enable_phone_notifications',
    'enable_document_to_booking',
    'enable_email_to_booking',
    'enable_hbl_generation',
    'enable_tracking',
]

# Default booking form fields that can be controlled by FieldConfig.
# Labels and required can be customised on all of these.
CONFIGURABLE_FIELDS = [
    'transport_mode', 'service_type', 'move_type',
    'origin_port', 'destination_port', 'cargo_ready_date',
    'container_type', 'container_count',
    'lcl_consolidation_number', 'chargeable_weight_kg', 'flight_number',
    'incoterms', 'incoterms_location',
    'commodity_description', 'is_hazardous',
    'external_reference', 'special_instructions',
]

# Fields that CANNOT be hidden — structurally required (NOT NULL) or mode-critical.
# FieldConfig can still customise their label/required but not visibility.
UNHIDEABLE_FIELDS = frozenset([
    'transport_mode', 'origin_port', 'destination_port', 'cargo_ready_date',
    'container_type', 'container_count', 'incoterms',
])


_ALL_ENABLED = {flag: True for flag in FEATURE_FLAGS}
_NO_CONFIG_SENTINEL = '__no_config__'


class FeatureFlagService:
    """Check organization-level feature toggles."""

    @staticmethod
    def get_all_flags(organization):
        """Return dict of {feature_name: bool} for all feature flags.

        Caches a plain dict (not ORM object) for safety with all cache backends.
        Returns all-True if no config exists.
        """
        if organization is None:
            return dict(_ALL_ENABLED)
        cache_key = f'org_features:{organization.pk}'
        result = cache.get(cache_key)
        if result is None:
            from bookings.models import OrganizationFeatureConfig
            try:
                cfg = OrganizationFeatureConfig.objects.get(
                    organization=organization)
                result = {flag: getattr(cfg, flag, True) for flag in FEATURE_FLAGS}
            except OrganizationFeatureConfig.DoesNotExist:
                result = _NO_CONFIG_SENTINEL
            cache.set(cache_key, result, _FEATURE_CACHE_TTL)
        if result == _NO_CONFIG_SENTINEL:
            return dict(_ALL_ENABLED)
        return result

    @staticmethod
    def is_enabled(organization, feature_name):
        """Check if a feature is enabled for an organization.

        Returns True if no config exists (all features on by default).
        Raises ValueError if feature_name is not a known flag.
        """
        if feature_name not in FEATURE_FLAGS:
            raise ValueError(f'Unknown feature flag: {feature_name!r}')
        return FeatureFlagService.get_all_flags(organization).get(feature_name, True)

    @staticmethod
    def invalidate_cache(organization_id):
        """Clear cached feature config for an organization."""
        cache.delete(f'org_features:{organization_id}')


class FieldConfigService:
    """Manage per-customer field visibility and requirements."""

    @staticmethod
    def get_field_config(customer):
        """Return the FieldConfig.config dict, or empty dict."""
        if customer is None:
            return {}
        cache_key = f'field_config:{customer.pk}'
        result = cache.get(cache_key)
        if result is None:
            from bookings.models import FieldConfig
            try:
                fc = FieldConfig.objects.get(customer=customer)
                result = fc.config or {}
            except FieldConfig.DoesNotExist:
                result = {}
            cache.set(cache_key, result, _FIELD_CACHE_TTL)
        return result

    @staticmethod
    def get_visible_fields(customer):
        """Return list of field names visible for this customer.

        Fields not mentioned in config are visible by default.
        """
        config = FieldConfigService.get_field_config(customer)
        visible = []
        for field in CONFIGURABLE_FIELDS:
            field_cfg = config.get(field, {})
            if field_cfg.get('visible', True):
                visible.append(field)
        return visible

    @staticmethod
    def get_required_fields(customer):
        """Return list of field names required for this customer.

        Fields not mentioned in config keep their form-level defaults.
        Only returns fields explicitly marked required=True in config.
        """
        config = FieldConfigService.get_field_config(customer)
        required = []
        for field in CONFIGURABLE_FIELDS:
            field_cfg = config.get(field, {})
            if field_cfg.get('required', False):
                required.append(field)
        return required

    @staticmethod
    def get_field_label(customer, field_name):
        """Return custom label for a field, or None to use default."""
        config = FieldConfigService.get_field_config(customer)
        field_cfg = config.get(field_name, {})
        return field_cfg.get('label') or None

    @staticmethod
    def is_field_visible(customer, field_name):
        """Check if a specific field is visible for this customer."""
        config = FieldConfigService.get_field_config(customer)
        field_cfg = config.get(field_name, {})
        return field_cfg.get('visible', True)

    @staticmethod
    def invalidate_cache(customer_id):
        """Clear cached field config for a customer."""
        cache.delete(f'field_config:{customer_id}')
