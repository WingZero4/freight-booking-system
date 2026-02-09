from django.contrib import admin
from .models import IntegrationConfig, IntegrationLog, CarrierConfig


@admin.register(IntegrationConfig)
class IntegrationConfigAdmin(admin.ModelAdmin):
    list_display = [
        'customer', 'adapter_type', 'api_endpoint',
        'auth_type', 'auto_push_on_confirm', 'is_active',
    ]
    list_filter = ['adapter_type', 'auth_type', 'is_active', 'auto_push_on_confirm']
    search_fields = ['customer__name', 'customer__code', 'api_endpoint']
    list_select_related = ['customer']

    fieldsets = (
        (None, {
            'fields': ('customer', 'adapter_type', 'is_active', 'auto_push_on_confirm')
        }),
        ('Connection', {
            'fields': ('api_endpoint', 'auth_type', 'api_key', 'api_secret')
        }),
        ('Advanced', {
            'fields': ('extra_config',),
            'classes': ('collapse',)
        }),
    )


@admin.register(CarrierConfig)
class CarrierConfigAdmin(admin.ModelAdmin):
    list_display = [
        'carrier_code', 'carrier_name', 'carrier_type',
        'adapter_type', 'api_endpoint', 'supports_async_callback',
        'auto_chain_to_fms', 'is_active',
    ]
    list_filter = ['carrier_type', 'adapter_type', 'is_active',
                   'supports_async_callback', 'auto_chain_to_fms']
    search_fields = ['carrier_code', 'carrier_name']

    fieldsets = (
        (None, {
            'fields': ('carrier_code', 'carrier_name', 'carrier_type', 'is_active')
        }),
        ('API Connection', {
            'fields': ('adapter_type', 'api_endpoint', 'auth_type',
                       'api_key', 'api_secret')
        }),
        ('Behavior', {
            'fields': ('supports_async_callback', 'auto_chain_to_fms',
                       'callback_secret')
        }),
        ('Advanced', {
            'fields': ('extra_config',),
            'classes': ('collapse',)
        }),
    )


@admin.register(IntegrationLog)
class IntegrationLogAdmin(admin.ModelAdmin):
    list_display = [
        'booking', 'event', 'adapter_type', 'http_status', 'created_at',
    ]
    list_filter = ['event', 'adapter_type', 'http_status']
    search_fields = ['booking__booking_number', 'error_message']
    list_select_related = ['booking', 'config', 'carrier_config']
    readonly_fields = [
        'booking', 'config', 'carrier_config', 'event', 'adapter_type',
        'request_payload', 'response_payload',
        'http_status', 'error_message', 'created_at',
    ]
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
