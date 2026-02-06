from django.contrib import admin
from django.utils import timezone
from .models import Customer, UserProfile, Port, ContainerType, Booking, BookingItem, BookingDocument


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'email', 'city', 'country', 'is_active']
    list_filter = ['is_active', 'country']
    search_fields = ['code', 'name', 'email']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'get_email', 'customer', 'role', 'phone']
    list_filter = ['role', 'customer']
    search_fields = ['user__username', 'user__email', 'customer__name', 'customer__code']
    list_select_related = ['user', 'customer']

    def get_email(self, obj):
        return obj.user.email
    get_email.short_description = 'Email'


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'country', 'is_active']
    list_filter = ['country', 'is_active']
    search_fields = ['code', 'name']


@admin.register(ContainerType)
class ContainerTypeAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'size_ft']
    ordering = ['size_ft', 'code']


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0
    fields = ['description', 'package_type', 'quantity', 'weight_kg']


class BookingDocumentInline(admin.TabularInline):
    model = BookingDocument
    extra = 0
    readonly_fields = ['original_filename', 'file_size', 'uploaded_by', 'uploaded_at']
    fields = ['document_type', 'file', 'original_filename', 'file_size',
              'uploaded_by', 'uploaded_at', 'notes']


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_number', 'customer', 'origin_port', 'destination_port',
                    'container_type', 'container_count', 'cargo_ready_date', 'status']
    list_filter = ['status', 'container_type', 'origin_port', 'destination_port']
    search_fields = ['booking_number', 'customer__name', 'customer__code']
    readonly_fields = ['booking_number', 'created_by', 'created_at', 'updated_at',
                       'submitted_at', 'confirmed_at', 'cancelled_at', 'cancelled_by']
    inlines = [BookingItemInline, BookingDocumentInline]

    fieldsets = (
        ('Booking Info', {
            'fields': ('booking_number', 'status', 'customer', 'created_by')
        }),
        ('Route', {
            'fields': ('origin_port', 'destination_port', 'cargo_ready_date')
        }),
        ('Container', {
            'fields': ('container_type', 'container_count')
        }),
        ('Carrier Details (Operations)', {
            'fields': ('carrier_name', 'vessel_name', 'voyage_number', 'etd', 'eta'),
            'classes': ('collapse',)
        }),
        ('Instructions', {
            'fields': ('special_instructions',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'submitted_at', 'confirmed_at',
                       'cancelled_at', 'cancelled_by'),
            'classes': ('collapse',)
        }),
    )

    actions = ['confirm_bookings', 'cancel_bookings']

    @admin.action(description='Confirm selected bookings')
    def confirm_bookings(self, request, queryset):
        count = 0
        for booking in queryset.filter(status='SUBMITTED'):
            booking.confirm()
            count += 1
        self.message_user(request, f'{count} booking(s) confirmed.')

    @admin.action(description='Cancel selected bookings')
    def cancel_bookings(self, request, queryset):
        count = 0
        for booking in queryset.filter(status__in=['DRAFT', 'SUBMITTED']):
            booking.cancel(user=request.user)
            count += 1
        self.message_user(request, f'{count} booking(s) cancelled.')


@admin.register(BookingItem)
class BookingItemAdmin(admin.ModelAdmin):
    list_display = ['booking', 'description', 'package_type', 'quantity', 'weight_kg']
    search_fields = ['booking__booking_number', 'description']


@admin.register(BookingDocument)
class BookingDocumentAdmin(admin.ModelAdmin):
    list_display = ['booking', 'document_type', 'original_filename',
                    'file_size_display', 'uploaded_by', 'uploaded_at']
    list_filter = ['document_type']
    search_fields = ['booking__booking_number', 'original_filename']
    readonly_fields = ['original_filename', 'file_size', 'uploaded_by', 'uploaded_at']
