from django.contrib import admin
from django.utils import timezone
from .models import (
    Customer, UserProfile, Port, ContainerType, Carrier,
    Booking, BookingItem, BookingDocument,
    Party, BookingParty, AuditLog, Notification, BookingTemplate,
    ShipmentMilestone,
)
from .services import BookingService


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'email', 'city', 'country', 'is_active']
    list_filter = ['is_active', 'country']
    search_fields = ['code', 'name', 'email']
    fieldsets = (
        (None, {'fields': ('code', 'name', 'email', 'phone', 'is_active')}),
        ('Address', {'fields': ('address', 'city', 'country')}),
        ('Branding', {
            'fields': ('logo', 'primary_color', 'accent_color', 'portal_name'),
            'description': 'Customize the portal appearance for this customer. '
                           'Colors should be hex codes (e.g. #1E2A4A). '
                           'Logo recommended: 200x50px PNG with transparent background.',
        }),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_email', 'customer', 'role', 'phone', 'timezone', 'approval_status']
    list_filter = ['role', 'customer', 'approval_status']
    search_fields = ['user__username', 'user__email', 'customer__name', 'customer__code']
    list_select_related = ['user', 'customer']
    readonly_fields = ['approved_by', 'approved_at']
    actions = ['approve_registrations']

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'

    @admin.action(description='Approve selected registrations')
    def approve_registrations(self, request, queryset):
        count = 0
        for profile in queryset.filter(approval_status='PENDING'):
            profile.approval_status = 'APPROVED'
            profile.approved_by = request.user
            profile.approved_at = timezone.now()
            profile.save()
            profile.user.is_active = True
            profile.user.save()
            if profile.customer:
                profile.customer.is_active = True
                profile.customer.save()
            count += 1
        self.message_user(request, f'{count} registration(s) approved.')


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'country', 'region', 'is_active']
    list_filter = ['region', 'country', 'is_active']
    search_fields = ['code', 'name']


@admin.register(ContainerType)
class ContainerTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'size_ft']
    ordering = ['size_ft', 'code']


@admin.register(Carrier)
class CarrierAdmin(admin.ModelAdmin):
    list_display = ['scac_code', 'name', 'carrier_type', 'is_active']
    list_filter = ['carrier_type', 'is_active']
    search_fields = ['scac_code', 'name']


# ─── Booking inlines ─────────────────────────────────────────────────

class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0
    fields = [
        'description', 'package_type', 'quantity', 'weight_kg',
        'hs_code', 'volume_cbm', 'country_of_origin',
        'is_hazardous', 'un_number', 'imo_class',
    ]


class BookingDocumentInline(admin.TabularInline):
    model = BookingDocument
    extra = 0
    readonly_fields = ['original_filename', 'file_size', 'uploaded_by', 'uploaded_at']
    fields = ['document_type', 'file', 'original_filename', 'file_size',
              'uploaded_by', 'uploaded_at', 'notes']


class BookingPartyInline(admin.TabularInline):
    model = BookingParty
    extra = 0
    readonly_fields = ['company_name', 'contact_name', 'address_text', 'email', 'phone', 'tax_id', 'created_at']
    fields = ['role', 'party', 'company_name', 'contact_name', 'address_text', 'email', 'phone', 'tax_id']


class ShipmentMilestoneInline(admin.TabularInline):
    model = ShipmentMilestone
    extra = 0
    readonly_fields = ['milestone_type', 'occurred_at', 'location', 'notes', 'recorded_by', 'created_at']
    fields = ['milestone_type', 'occurred_at', 'location', 'notes', 'recorded_by', 'created_at']
    ordering = ['occurred_at']
    max_num = 0  # Read-only — managed via ops views


class AuditLogInline(admin.TabularInline):
    model = AuditLog
    extra = 0
    readonly_fields = ['action', 'performed_by', 'performed_at', 'notes']
    fields = ['action', 'performed_by', 'performed_at', 'notes']
    ordering = ['-performed_at']
    max_num = 0  # Read-only — no adding from admin


# ─── Booking admin ────────────────────────────────────────────────────

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = [
        'booking_number', 'customer', 'transport_mode',
        'origin_port', 'destination_port',
        'container_display',
        'cargo_ready_date', 'status',
    ]
    list_filter = ['status', 'transport_mode', 'incoterms', 'source_channel',
                   'is_hazardous', 'container_type', 'origin_port', 'destination_port']
    search_fields = ['booking_number', 'customer__name', 'customer__code',
                     'external_reference', 'carrier_booking_ref', 'contract_number',
                     'fms_shipment_id', 'hbl_number', 'mbl_number']
    readonly_fields = [
        'booking_number', 'created_by', 'source_channel',
        'total_weight_kg', 'total_volume_cbm',
        'created_at', 'updated_at', 'submitted_at', 'confirmed_at',
        'packing_at', 'customer_approved_by',
        'customer_rejected_at', 'customer_rejected_by', 'customer_rejection_reason',
        'in_transit_at', 'arrived_at', 'confirmed_by',
        'rejected_at', 'rejected_by', 'rejection_reason',
        'completed_at', 'cancelled_at', 'cancelled_by', 'cancellation_reason',
        'actual_departure_date', 'actual_arrival_date',
        'fms_shipment_id', 'hbl_number', 'mbl_number',
        'hawb_number', 'mawb_number',
        'fms_push_status', 'fms_push_error',
        'carrier_request_status', 'carrier_request_error',
        'carrier_confirmation_ref', 'container_numbers',
    ]
    inlines = [BookingItemInline, BookingPartyInline, BookingDocumentInline, ShipmentMilestoneInline, AuditLogInline]

    fieldsets = (
        ('Booking Info', {
            'fields': ('booking_number', 'status', 'customer', 'created_by',
                       'source_channel', 'external_reference')
        }),
        ('Route & Mode', {
            'fields': ('transport_mode', 'origin_port', 'destination_port',
                       'cargo_ready_date')
        }),
        ('Trade Terms', {
            'fields': ('incoterms', 'incoterms_location')
        }),
        ('Container / Equipment', {
            'fields': ('container_type', 'container_count',
                       'lcl_consolidation_number',
                       'chargeable_weight_kg', 'flight_number'),
            'description': 'Container fields for FCL; consolidation for LCL; weight/flight for Air',
        }),
        ('Cargo Summary', {
            'fields': ('commodity_description', 'is_hazardous',
                       'total_weight_kg', 'total_volume_cbm')
        }),
        ('Carrier Details (Operations)', {
            'fields': ('carrier_name', 'vessel_name', 'voyage_number',
                       'cargo_cutoff_date', 'etd', 'eta',
                       'carrier_booking_ref', 'contract_number'),
            'classes': ('collapse',)
        }),
        ('Instructions', {
            'fields': ('special_instructions',)
        }),
        ('Carrier Integration', {
            'fields': ('carrier_config', 'carrier_request_status',
                       'carrier_request_error', 'carrier_confirmation_ref',
                       'container_numbers'),
            'classes': ('collapse',)
        }),
        ('FMS Integration', {
            'fields': ('fms_shipment_id', 'hbl_number', 'mbl_number',
                       'hawb_number', 'mawb_number',
                       'fms_push_status', 'fms_push_error'),
            'classes': ('collapse',)
        }),
        ('Status Details', {
            'fields': ('confirmed_by', 'cancellation_reason',
                       'actual_departure_date', 'actual_arrival_date'),
            'classes': ('collapse',)
        }),
        ('Customer Approval', {
            'fields': ('packing_at', 'customer_approved_by',
                       'customer_rejected_at', 'customer_rejected_by',
                       'customer_rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'submitted_at', 'confirmed_at',
                       'in_transit_at', 'arrived_at',
                       'rejected_at', 'rejected_by', 'rejection_reason',
                       'completed_at', 'cancelled_at', 'cancelled_by'),
            'classes': ('collapse',)
        }),
    )

    @admin.display(description='Container')
    def container_display(self, obj):
        if obj.container_type and obj.container_count:
            return f"{obj.container_count}x {obj.container_type.code}"
        elif obj.container_type:
            return obj.container_type.code
        return '-'

    actions = ['confirm_bookings', 'cancel_bookings']

    @admin.action(description='Confirm selected bookings')
    def confirm_bookings(self, request, queryset):
        count = 0
        for booking in queryset.filter(status='SUBMITTED'):
            BookingService.confirm_booking(booking, user=request.user, request=request)
            count += 1
        self.message_user(request, f'{count} booking(s) confirmed.')

    @admin.action(description='Cancel selected bookings')
    def cancel_bookings(self, request, queryset):
        count = 0
        for booking in queryset.filter(status__in=['DRAFT', 'SUBMITTED']):
            BookingService.cancel_booking(booking, user=request.user, request=request)
            count += 1
        self.message_user(request, f'{count} booking(s) cancelled.')


@admin.register(BookingItem)
class BookingItemAdmin(admin.ModelAdmin):
    list_display = ['get_booking_number', 'get_customer', 'description',
                    'package_type', 'quantity', 'weight_kg', 'volume_cbm',
                    'hs_code', 'is_hazardous']
    list_filter = ['package_type', 'is_hazardous', 'booking__customer']
    search_fields = ['booking__booking_number', 'description', 'hs_code',
                     'booking__customer__name', 'booking__customer__code']
    list_select_related = ['booking__customer']

    @admin.display(description='Booking #', ordering='booking__booking_number')
    def get_booking_number(self, obj):
        return obj.booking.booking_number

    @admin.display(description='Customer', ordering='booking__customer__name')
    def get_customer(self, obj):
        return f"{obj.booking.customer.name} ({obj.booking.customer.code})"



@admin.register(BookingDocument)
class BookingDocumentAdmin(admin.ModelAdmin):
    list_display = ['booking', 'document_type', 'original_filename',
                    'get_file_size_display', 'uploaded_by', 'uploaded_at']
    list_filter = ['document_type']
    search_fields = ['booking__booking_number', 'original_filename']
    readonly_fields = ['original_filename', 'file_size', 'uploaded_by', 'uploaded_at']

    @admin.display(description='File Size')
    def get_file_size_display(self, obj):
        return obj.file_size_display


# ─── New Phase 1.5 models ────────────────────────────────────────────

@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'role', 'customer', 'contact_name',
                    'email', 'country_code', 'is_default', 'is_active']
    list_filter = ['role', 'is_default', 'is_active', 'country_code']
    search_fields = ['company_name', 'contact_name', 'email', 'customer__name']
    list_select_related = ['customer']


@admin.register(BookingParty)
class BookingPartyAdmin(admin.ModelAdmin):
    list_display = ['booking', 'role', 'company_name', 'contact_name', 'email']
    list_filter = ['role']
    search_fields = ['booking__booking_number', 'company_name']
    list_select_related = ['booking', 'party']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['booking', 'action', 'performed_by', 'performed_at']
    list_filter = ['action']
    search_fields = ['booking__booking_number', 'notes']
    readonly_fields = [
        'booking', 'action', 'performed_by', 'performed_at',
        'old_value', 'new_value', 'ip_address', 'user_agent', 'notes',
    ]
    list_select_related = ['booking', 'performed_by']
    date_hierarchy = 'performed_at'

    def has_add_permission(self, request):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'notification_type', 'message_preview', 'booking', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']
    search_fields = ['user__username', 'message', 'booking__booking_number']
    list_select_related = ['user', 'booking']
    readonly_fields = [
        'user', 'booking', 'message', 'notification_type', 'is_read', 'created_at',
    ]
    date_hierarchy = 'created_at'

    @admin.display(description='Message')
    def message_preview(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BookingTemplate)
class BookingTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer', 'created_by', 'created_at', 'updated_at']
    list_filter = ['customer']
    search_fields = ['name', 'customer__name', 'customer__code']
    list_select_related = ['customer', 'created_by']
    readonly_fields = ['template_data', 'created_by', 'created_at', 'updated_at']


@admin.register(ShipmentMilestone)
class ShipmentMilestoneAdmin(admin.ModelAdmin):
    list_display = ['booking', 'milestone_type', 'occurred_at', 'location', 'recorded_by']
    list_filter = ['milestone_type']
    search_fields = ['booking__booking_number', 'location', 'notes']
    list_select_related = ['booking', 'recorded_by']
    raw_id_fields = ['booking']
