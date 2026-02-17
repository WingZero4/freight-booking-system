import os
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import FileExtensionValidator, RegexValidator


class Customer(models.Model):
    """Shipper company"""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Branding / White-label
    hex_color_validator = RegexValidator(
        r'^#[0-9A-Fa-f]{6}$', 'Enter a valid hex color code (e.g. #1E2A4A).')
    logo = models.ImageField(
        upload_to='customer_logos/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp'])],
        help_text='Company logo (recommended: 200x50px PNG with transparent bg)')
    primary_color = models.CharField(
        max_length=7, blank=True, default='',
        validators=[hex_color_validator],
        help_text='Primary brand color hex, e.g. #1E2A4A')
    accent_color = models.CharField(
        max_length=7, blank=True, default='',
        validators=[hex_color_validator],
        help_text='Accent/button color hex, e.g. #DC3545')
    portal_name = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Custom portal name shown in navbar')

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['name']


class UserProfile(models.Model):
    """Link Django user to customer"""
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('USER', 'User'),
        ('OPERATIONS', 'Operations'),
        ('SALES', 'Sales'),
    ]

    APPROVAL_STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USER')
    phone = models.CharField(max_length=50, blank=True)
    approval_status = models.CharField(
        max_length=20, choices=APPROVAL_STATUS_CHOICES, default='APPROVED',
    )
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_profiles',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    timezone = models.CharField(
        max_length=50, blank=True, default='',
        help_text='IANA timezone name, e.g. Asia/Singapore. Blank = UTC.',
    )

    def __str__(self):
        if self.customer:
            return f"{self.user.username} ({self.customer.code})"
        return f"{self.user.username} (Staff)"

    @property
    def is_staff_user(self):
        return self.customer is None


class Party(models.Model):
    """Address book entry for shippers, consignees, notify parties, etc."""
    ROLE_CHOICES = [
        ('SHIPPER', 'Shipper'),
        ('CONSIGNEE', 'Consignee'),
        ('NOTIFY', 'Notify Party'),
        ('BROKER', 'Customs Broker'),
        ('FREIGHT_FORWARDER', 'Freight Forwarder'),
        ('OTHER', 'Other'),
    ]

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name='parties',
        help_text='The customer account that owns this party record'
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(
        max_length=2, blank=True,
        help_text='ISO 3166-1 alpha-2 country code (e.g. US, CN, DE)'
    )
    tax_id = models.CharField(max_length=50, blank=True, help_text='Tax ID / VAT number')
    is_default = models.BooleanField(
        default=False,
        help_text='Default party for this role under this customer'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.company_name} ({self.get_role_display()})"

    @property
    def full_address(self):
        parts = [self.address_line_1, self.address_line_2, self.city,
                 self.state, self.postal_code, self.country_code]
        return ', '.join(p for p in parts if p)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.is_default and self.customer_id:
                # Atomically clear any existing default for this customer+role
                Party.objects.filter(
                    customer_id=self.customer_id,
                    role=self.role,
                    is_default=True,
                ).exclude(pk=self.pk).select_for_update().update(is_default=False)
            super().save(*args, **kwargs)

    class Meta:
        ordering = ['company_name']
        verbose_name_plural = 'parties'


class Port(models.Model):
    """Ports (sea, air, rail)"""
    REGION_CHOICES = [
        ('EAST_ASIA', 'East Asia'),
        ('SOUTHEAST_ASIA', 'Southeast Asia'),
        ('SOUTH_ASIA', 'South Asia'),
        ('MIDDLE_EAST', 'Middle East'),
        ('EUROPE', 'Europe'),
        ('NORTH_AMERICA', 'North America'),
        ('SOUTH_AMERICA', 'South America'),
        ('AFRICA', 'Africa'),
        ('OCEANIA', 'Oceania'),
    ]

    code = models.CharField(max_length=10, unique=True)  # UN/LOCODE
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=30, choices=REGION_CHOICES, default='NORTH_AMERICA')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['country', 'name']


class ContainerType(models.Model):
    """Container specifications"""
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    size_ft = models.IntegerField()

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        ordering = ['size_ft', 'code']


class Carrier(models.Model):
    """Shipping line / airline reference data"""
    CARRIER_TYPE_CHOICES = [
        ('OCEAN', 'Ocean Carrier'),
        ('AIR', 'Air Carrier'),
        ('RAIL', 'Rail Carrier'),
        ('TRUCKING', 'Trucking Carrier'),
    ]

    scac_code = models.CharField(
        max_length=10, unique=True,
        help_text='SCAC code for ocean, IATA code for air',
    )
    name = models.CharField(max_length=100)
    carrier_type = models.CharField(max_length=20, choices=CARRIER_TYPE_CHOICES, default='OCEAN')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"[{self.scac_code}] {self.name}"

    class Meta:
        ordering = ['name']


class Booking(models.Model):
    """Freight Booking"""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('CONFIRMED', 'Confirmed'),
        ('CUSTOMER_REJECTED', 'Customer Rejected'),
        ('REJECTED', 'Rejected'),
        ('PACKING', 'Packing'),
        ('IN_TRANSIT', 'In Transit'),
        ('ARRIVED', 'Arrived'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    TRANSPORT_MODE_CHOICES = [
        ('SEA_FCL', 'Sea - FCL'),
        ('SEA_LCL', 'Sea - LCL'),
        ('AIR', 'Air Freight'),
        ('RAIL', 'Rail'),
        ('TRUCK', 'Trucking'),
        ('MULTIMODAL', 'Multimodal'),
    ]

    INCOTERMS_CHOICES = [
        ('FOB', 'FOB - Free on Board'),
        ('CFR', 'CFR - Cost and Freight'),
        ('CIF', 'CIF - Cost, Insurance and Freight'),
        ('EXW', 'EXW - Ex Works'),
        ('FCA', 'FCA - Free Carrier'),
        ('CPT', 'CPT - Carriage Paid To'),
        ('CIP', 'CIP - Carriage and Insurance Paid To'),
        ('DAP', 'DAP - Delivered at Place'),
        ('DPU', 'DPU - Delivered at Place Unloaded'),
        ('DDP', 'DDP - Delivered Duty Paid'),
        ('FAS', 'FAS - Free Alongside Ship'),
    ]

    SOURCE_CHANNEL_CHOICES = [
        ('WEB', 'Web Portal'),
        ('API', 'API'),
        ('EDI', 'EDI'),
        ('CSV', 'CSV/XLSX Import'),
        ('MANUAL', 'Manual Entry'),
    ]

    # Auto-generated booking number
    booking_number = models.CharField(max_length=20, unique=True, editable=False)

    # Transport mode
    transport_mode = models.CharField(
        max_length=20, choices=TRANSPORT_MODE_CHOICES, default='SEA_FCL',
        help_text='Mode of transport for this shipment'
    )

    # Customer
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_bookings')

    # Route
    origin_port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name='origin_bookings')
    destination_port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name='destination_bookings')

    # Dates
    cargo_ready_date = models.DateField()
    cargo_cutoff_date = models.DateField(
        null=True, blank=True,
        help_text='Deadline for cargo to arrive at port/terminal (set by operations)'
    )

    # Container (required for Sea FCL only)
    container_type = models.ForeignKey(
        ContainerType, on_delete=models.PROTECT,
        null=True, blank=True,
        help_text='Container type (required for FCL shipments)'
    )
    container_count = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Number of containers (required for FCL shipments)'
    )

    # LCL consolidation (Sea LCL only)
    lcl_consolidation_number = models.CharField(
        max_length=50, blank=True,
        help_text='Consolidation number for LCL shipments (assigned by forwarder)'
    )

    # Trade terms (Phase 1.5)
    incoterms = models.CharField(
        max_length=3, choices=INCOTERMS_CHOICES, default='FOB',
        help_text='INCOTERMS 2020 trade terms'
    )
    incoterms_location = models.CharField(
        max_length=255, blank=True,
        help_text='Named place for the selected INCOTERM (e.g. port or warehouse)'
    )

    # Cargo summary (Phase 1.5)
    commodity_description = models.CharField(
        max_length=500, blank=True,
        help_text='General description of goods being shipped'
    )
    is_hazardous = models.BooleanField(
        default=False,
        help_text='Does this booking contain any hazardous materials?'
    )
    total_weight_kg = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Total cargo weight in kg (auto-calculated from items)'
    )
    total_volume_cbm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Total cargo volume in cubic meters (auto-calculated from items)'
    )

    # Air freight fields
    chargeable_weight_kg = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Chargeable weight in kg (max of actual vs volumetric weight)'
    )
    flight_number = models.CharField(
        max_length=20, blank=True,
        help_text='Flight number for air freight (e.g. CX890)'
    )

    # Integration tracking (Phase 1.5)
    source_channel = models.CharField(
        max_length=10, choices=SOURCE_CHANNEL_CHOICES, default='WEB'
    )
    external_reference = models.CharField(
        max_length=100,
        help_text='Customer or external system reference number (required)'
    )
    carrier_booking_ref = models.CharField(
        max_length=100, blank=True,
        help_text='Carrier-assigned booking reference'
    )

    # FMS integration
    fms_shipment_id = models.CharField(
        max_length=100, blank=True,
        help_text='Shipment ID in external FMS'
    )
    hbl_number = models.CharField(
        max_length=50, blank=True,
        help_text='House Bill of Lading number'
    )
    mbl_number = models.CharField(
        max_length=50, blank=True,
        help_text='Master Bill of Lading number'
    )
    hawb_number = models.CharField(
        max_length=50, blank=True,
        help_text='House Airway Bill number'
    )
    mawb_number = models.CharField(
        max_length=50, blank=True,
        help_text='Master Airway Bill number'
    )
    FMS_PUSH_STATUS_CHOICES = [
        ('', 'Not Configured'),
        ('PENDING', 'Pending'),
        ('PUSHED', 'Pushed'),
        ('FAILED', 'Failed'),
        ('CALLBACK_RECEIVED', 'Callback Received'),
    ]
    fms_push_status = models.CharField(
        max_length=20, blank=True, default='',
        choices=FMS_PUSH_STATUS_CHOICES,
        help_text='Status of FMS integration push'
    )
    fms_push_error = models.TextField(
        blank=True,
        help_text='Last FMS push error message'
    )

    # Carrier integration
    carrier_config = models.ForeignKey(
        'integrations.CarrierConfig', on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='bookings',
        help_text='Carrier API config used for this booking'
    )
    CARRIER_REQUEST_STATUS_CHOICES = [
        ('', 'Not Submitted'),
        ('PENDING', 'Pending Submission'),
        ('SUBMITTED', 'Submitted to Carrier'),
        ('CONFIRMED', 'Carrier Confirmed'),
        ('REJECTED', 'Carrier Rejected'),
        ('FAILED', 'Submission Failed'),
        ('CANCELLED', 'Cancelled with Carrier'),
    ]
    carrier_request_status = models.CharField(
        max_length=20, blank=True, default='',
        choices=CARRIER_REQUEST_STATUS_CHOICES,
        help_text='Status of carrier API booking request'
    )
    carrier_request_error = models.TextField(
        blank=True,
        help_text='Last carrier API error message'
    )
    carrier_confirmation_ref = models.CharField(
        max_length=100, blank=True,
        help_text='Carrier-side confirmation reference from their API'
    )
    container_numbers = models.TextField(
        blank=True,
        help_text='Carrier-assigned container numbers (one per line)'
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Notes
    special_instructions = models.TextField(blank=True)

    # Carrier info (filled by operations)
    carrier_name = models.CharField(max_length=100, blank=True)
    vessel_name = models.CharField(max_length=100, blank=True)
    voyage_number = models.CharField(max_length=50, blank=True)
    contract_number = models.CharField(
        max_length=100, blank=True,
        help_text='Internal carrier contract number (not visible to customers)'
    )
    etd = models.DateField(null=True, blank=True, verbose_name="ETD")
    eta = models.DateField(null=True, blank=True, verbose_name="ETA")

    # Actual dates (recorded at status transitions)
    actual_departure_date = models.DateField(
        null=True, blank=True,
        help_text='Actual date vessel/flight departed (set when marking in transit)'
    )
    actual_arrival_date = models.DateField(
        null=True, blank=True,
        help_text='Actual date cargo arrived at destination (set when completing)'
    )

    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='confirmed_bookings'
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='rejected_bookings'
    )
    rejection_reason = models.TextField(blank=True)
    packing_at = models.DateTimeField(null=True, blank=True)
    customer_approved_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='customer_approved_bookings'
    )
    customer_rejected_at = models.DateTimeField(null=True, blank=True)
    customer_rejected_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='customer_rejected_bookings'
    )
    customer_rejection_reason = models.TextField(blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cancelled_bookings'
    )
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.booking_number} ({self.status})"

    @property
    def requires_container(self):
        return self.transport_mode == 'SEA_FCL'

    def save(self, *args, **kwargs):
        if not self.booking_number:
            self.booking_number = self._generate_booking_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_booking_number():
        """Generate booking number: BK-YYYYMM-NNNN (thread-safe)"""
        today = timezone.now()
        prefix = f"BK-{today.strftime('%Y%m')}-"

        with transaction.atomic():
            # Lock matching rows to prevent race conditions
            last = (
                Booking.objects.select_for_update()
                .filter(booking_number__startswith=prefix)
                .order_by('-booking_number')
                .first()
            )

            if last:
                last_num = int(last.booking_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1

        return f"{prefix}{new_num:04d}"

    def recalculate_totals(self):
        """Recalculate total_weight_kg and total_volume_cbm from items."""
        from decimal import Decimal
        from django.db.models import Sum
        totals = self.items.aggregate(
            weight=Sum('weight_kg'),
            volume=Sum('volume_cbm'),
        )
        self.total_weight_kg = totals['weight'] or Decimal('0.00')
        self.total_volume_cbm = totals['volume'] or Decimal('0.000')
        self.save(update_fields=['total_weight_kg', 'total_volume_cbm', 'updated_at'])

    def submit(self):
        """Submit booking for processing. Requires at least one cargo item."""
        if self.status != 'DRAFT':
            return
        if not self.items.exists():
            raise ValueError('Cannot submit a booking with no cargo items.')
        self.recalculate_totals()
        self.status = 'SUBMITTED'
        self.submitted_at = timezone.now()
        self.save()

    def confirm(self, user=None):
        """Confirm booking (operations action)."""
        if self.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be confirmed.')
        self.status = 'CONFIRMED'
        self.confirmed_at = timezone.now()
        if user:
            self.confirmed_by = user
        self.save()

    def reject(self, user=None, reason=''):
        """Reject a submitted booking."""
        if self.status != 'SUBMITTED':
            raise ValueError('Only submitted bookings can be rejected.')
        self.status = 'REJECTED'
        self.rejected_at = timezone.now()
        if user:
            self.rejected_by = user
        self.rejection_reason = reason
        self.save()

    def mark_in_transit(self):
        """Mark packing booking as in transit."""
        if self.status != 'PACKING':
            raise ValueError('Only packing bookings can be marked in transit.')
        self.status = 'IN_TRANSIT'
        self.in_transit_at = timezone.now()
        self.save()

    def mark_arrived(self):
        """Mark in-transit booking as arrived at destination."""
        if self.status != 'IN_TRANSIT':
            raise ValueError('Only in-transit bookings can be marked as arrived.')
        self.status = 'ARRIVED'
        self.arrived_at = timezone.now()
        self.save()

    def complete(self):
        """Mark booking as completed."""
        if self.status not in ('IN_TRANSIT', 'ARRIVED'):
            raise ValueError('Only in-transit or arrived bookings can be completed.')
        self.status = 'COMPLETED'
        self.completed_at = timezone.now()
        self.save()

    def cancel(self, user=None, reason=''):
        """Cancel booking."""
        if self.status not in ('DRAFT', 'SUBMITTED', 'CONFIRMED', 'PACKING', 'CUSTOMER_REJECTED'):
            raise ValueError('This booking cannot be cancelled.')
        self.status = 'CANCELLED'
        self.cancelled_at = timezone.now()
        if user:
            self.cancelled_by = user
        if reason:
            self.cancellation_reason = reason
        self.save()

    class Meta:
        ordering = ['-created_at']


class BookingItem(models.Model):
    """Cargo items in a booking"""
    PACKAGE_TYPE_CHOICES = [
        ('PALLET', 'Pallet'),
        ('CARTON', 'Carton'),
        ('CRATE', 'Crate'),
        ('DRUM', 'Drum'),
        ('BAG', 'Bag'),
        ('BUNDLE', 'Bundle'),
        ('PACKAGE', 'Package'),
        ('OTHER', 'Other'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    package_type = models.CharField(max_length=50, choices=PACKAGE_TYPE_CHOICES, default='PACKAGE')
    quantity = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2)

    # Phase 1.5 fields
    hs_code = models.CharField(
        max_length=10, blank=True,
        help_text='Harmonized System code (6-10 digits)'
    )
    volume_cbm = models.DecimalField(
        max_digits=10, decimal_places=3, null=True, blank=True,
        help_text='Volume in cubic meters'
    )
    length_cm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Length in centimeters'
    )
    width_cm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Width in centimeters'
    )
    height_cm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text='Height in centimeters'
    )
    marks_and_numbers = models.CharField(
        max_length=500, blank=True,
        help_text='Shipping marks and package numbers'
    )
    is_hazardous = models.BooleanField(default=False)
    un_number = models.CharField(
        max_length=4, blank=True,
        help_text='UN number for hazardous goods (e.g. 1234)'
    )
    imo_class = models.CharField(
        max_length=10, blank=True,
        help_text='IMO hazard class (e.g. 3, 6.1, 8)'
    )
    country_of_origin = models.CharField(
        max_length=2, blank=True,
        help_text='ISO 3166-1 alpha-2 country code'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity}x {self.description} ({self.weight_kg}kg)"

    @property
    def calculated_volume_cbm(self):
        """Calculate volume from dimensions if all three are provided."""
        if self.length_cm and self.width_cm and self.height_cm:
            return (self.length_cm * self.width_cm * self.height_cm) / 1_000_000
        return self.volume_cbm

    class Meta:
        ordering = ['id']
        verbose_name = 'cargo line item'
        verbose_name_plural = 'cargo line items'


def booking_document_path(instance, filename):
    """Upload to: media/bookings/<booking_number>/<filename>"""
    return f"bookings/{instance.booking.booking_number}/{filename}"


class BookingDocument(models.Model):
    """Documents attached to a booking"""
    DOCUMENT_TYPE_CHOICES = [
        ('COMMERCIAL_INVOICE', 'Commercial Invoice'),
        ('PACKING_LIST', 'Packing List'),
        ('BILL_OF_LADING', 'Bill of Lading'),
        ('AIRWAY_BILL', 'Airway Bill'),
        ('CUSTOMS_DECLARATION', 'Customs Declaration'),
        ('CERTIFICATE_OF_ORIGIN', 'Certificate of Origin'),
        ('SHIPPING_ADVICE', 'Shipping Advice'),
        ('CARGO_MANIFEST', 'Cargo Manifest'),
        ('LOADING_PLAN', 'Loading Plan'),
        ('INSURANCE_CERTIFICATE', 'Insurance Certificate'),
        ('FUMIGATION_CERT', 'Fumigation Certificate'),
        ('INSPECTION_REPORT', 'Inspection Report'),
        ('OTHER', 'Other'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_TYPE_CHOICES)
    file = models.FileField(
        upload_to=booking_document_path,
        validators=[FileExtensionValidator(
            allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'xlsx', 'csv']
        )]
    )
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.original_filename}"

    @property
    def file_size_display(self):
        """Human-readable file size"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        return f"{self.file_size / (1024 * 1024):.1f} MB"

    @property
    def file_extension(self):
        return os.path.splitext(self.original_filename)[1].lower()

    class Meta:
        ordering = ['-uploaded_at']


class BookingParty(models.Model):
    """Snapshot of a party's details at the time they were assigned to a booking."""
    ROLE_CHOICES = [
        ('SHIPPER', 'Shipper'),
        ('CONSIGNEE', 'Consignee'),
        ('NOTIFY', 'Notify Party'),
        ('BROKER', 'Customs Broker'),
        ('FREIGHT_FORWARDER', 'Freight Forwarder'),
        ('OTHER', 'Other'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='booking_parties')
    party = models.ForeignKey(
        Party, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='booking_assignments',
        help_text='Link to the address book entry (null if party was deleted)'
    )
    role = models.CharField(max_length=30, choices=ROLE_CHOICES)

    # Snapshot fields — captured at assignment time so booking records are immutable
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    address_text = models.TextField(
        blank=True,
        help_text='Full address as a single text block (snapshot)'
    )
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_role_display()}: {self.company_name}"

    @classmethod
    def create_from_party(cls, booking, party, role=None):
        """Create a BookingParty snapshot from an address book Party."""
        return cls.objects.create(
            booking=booking,
            party=party,
            role=role or party.role,
            company_name=party.company_name,
            contact_name=party.contact_name,
            address_text=party.full_address,
            email=party.email,
            phone=party.phone,
            tax_id=party.tax_id,
        )

    class Meta:
        ordering = ['role', 'company_name']
        verbose_name_plural = 'booking parties'
        constraints = [
            models.UniqueConstraint(
                fields=['booking', 'role'],
                name='unique_party_role_per_booking'
            )
        ]


class AuditLog(models.Model):
    """Track all changes to bookings for compliance and traceability."""
    ACTION_CHOICES = [
        ('CREATED', 'Created'),
        ('UPDATED', 'Updated'),
        ('SUBMITTED', 'Submitted'),
        ('CONFIRMED', 'Confirmed'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('IN_TRANSIT', 'Marked In Transit'),
        ('ARRIVED', 'Arrived at Destination'),
        ('COMPLETED', 'Completed'),
        ('DOCUMENT_UPLOADED', 'Document Uploaded'),
        ('DOCUMENT_DELETED', 'Document Deleted'),
        ('PARTY_ADDED', 'Party Added'),
        ('PARTY_REMOVED', 'Party Removed'),
        ('ITEM_ADDED', 'Cargo Item Added'),
        ('ITEM_UPDATED', 'Cargo Item Updated'),
        ('ITEM_REMOVED', 'Cargo Item Removed'),
        ('RESUBMITTED', 'Resubmitted from Rejection'),
        ('CUSTOMER_APPROVED', 'Customer Approved'),
        ('CUSTOMER_REJECTED', 'Customer Rejected'),
        ('RECONFIRMED', 'Re-confirmed after Customer Rejection'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    performed_at = models.DateTimeField(default=timezone.now)
    old_value = models.JSONField(null=True, blank=True, help_text='Previous state (JSON)')
    new_value = models.JSONField(null=True, blank=True, help_text='New state (JSON)')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.booking.booking_number} - {self.get_action_display()} by {self.performed_by}"

    class Meta:
        ordering = ['-performed_at']
        verbose_name_plural = 'audit logs'


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('BOOKING_SUBMITTED', 'Booking Submitted'),
        ('BOOKING_CONFIRMED', 'Booking Confirmed'),
        ('BOOKING_REJECTED', 'Booking Rejected'),
        ('BOOKING_IN_TRANSIT', 'Booking In Transit'),
        ('BOOKING_ARRIVED', 'Booking Arrived'),
        ('BOOKING_COMPLETED', 'Booking Completed'),
        ('BOOKING_CANCELLED', 'Booking Cancelled'),
        ('BOOKING_RESUBMITTED', 'Booking Resubmitted'),
        ('BOOKING_CUSTOMER_APPROVED', 'Booking Customer Approved'),
        ('BOOKING_CUSTOMER_REJECTED', 'Booking Customer Rejected'),
        ('GENERAL', 'General'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    booking = models.ForeignKey(
        'Booking', on_delete=models.CASCADE, null=True, blank=True,
        related_name='notifications',
    )
    message = models.CharField(max_length=500)
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPES, default='GENERAL')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}: {self.message[:50]}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
        ]


class BookingTemplate(models.Model):
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='booking_templates')
    name = models.CharField(max_length=100)
    template_data = models.JSONField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer.code}: {self.name}"

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(fields=['customer', 'name'], name='unique_template_per_customer'),
        ]


class ShipmentMilestone(models.Model):
    """Event-based operational tracking for shipment lifecycle."""
    MILESTONE_CHOICES = [
        ('CARGO_RECEIVED', 'Cargo Received at Origin'),
        ('GATE_IN', 'Gate In at Terminal'),
        ('CUSTOMS_EXPORT', 'Export Customs Cleared'),
        ('LOADED', 'Loaded on Vessel/Flight'),
        ('DEPARTED', 'Departed Origin'),
        ('TRANSSHIPMENT', 'Transshipment'),
        ('ARRIVED_PORT', 'Arrived at Destination Port'),
        ('DISCHARGED', 'Discharged from Vessel'),
        ('CUSTOMS_IMPORT', 'Import Customs Cleared'),
        ('GATE_OUT', 'Gate Out from Terminal'),
        ('OUT_FOR_DELIVERY', 'Out for Delivery'),
        ('DELIVERED', 'Delivered to Consignee'),
        ('OTHER', 'Other'),
    ]

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='milestones')
    milestone_type = models.CharField(max_length=30, choices=MILESTONE_CHOICES)
    occurred_at = models.DateTimeField(help_text='When this milestone actually occurred')
    location = models.CharField(max_length=200, blank=True, help_text='Location/port where this occurred')
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.booking.booking_number} - {self.get_milestone_type_display()}"

    class Meta:
        ordering = ['occurred_at']
        verbose_name = 'shipment milestone'
