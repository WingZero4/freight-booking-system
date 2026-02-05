from django.contrib import admin
from django.utils import timezone
from .models import Customer, UserProfile, Port, ContainerType, Booking, BookingItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'email', 'city', 'country', 'is_active']
    list_filter = ['is_active', 'country']
    search_fields = ['code', 'name', 'email']


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'customer', 'role']
    list_filter = ['role']
    search_fields = ['user__username', 'customer__name']


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


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ['booking_number', 'customer', 'origin_port', 'destination_port',
                    'container_type', 'container_count', 'cargo_ready_date', 'status']
    list_filter = ['status', 'container_type', 'origin_port', 'destination_port']
    search_fields = ['booking_number', 'customer__name', 'customer__code']
    readonly_fields = ['booking_number', 'created_by', 'created_at', 'updated_at',
                       'submitted_at', 'confirmed_at']
    inlines = [BookingItemInline]

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
            'fields': ('created_at', 'updated_at', 'submitted_at', 'confirmed_at'),
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
            booking.cancel()
            count += 1
        self.message_user(request, f'{count} booking(s) cancelled.')


@admin.register(BookingItem)
class BookingItemAdmin(admin.ModelAdmin):
    list_display = ['booking', 'description', 'package_type', 'quantity', 'weight_kg']
    search_fields = ['booking__booking_number', 'description']
