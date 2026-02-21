import os
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, RegexValidator


# ─── Shared validators ──────────────────────────────────────────────
_hex_color_validator = RegexValidator(
    r'^#[0-9A-Fa-f]{6}$', 'Enter a valid hex color code (e.g. #1E2A4A).')


class Organization(models.Model):
    """Platform tenant / subscriber — the company that purchased access.

    Could be a freight forwarder, shipper, consignee, or any logistics company.
    Each Organization has its own companies, users, workflows, and branding.
    """
    ORG_TYPE_CHOICES = [
        ('FORWARDER', 'Freight Forwarder'),
        ('SHIPPER', 'Shipper'),
        ('CONSIGNEE', 'Consignee'),
        ('RETAILER', 'Retailer / Buyer'),
        ('OTHER', 'Other'),
    ]
    SUBSCRIPTION_TIER_CHOICES = [
        ('FREE', 'Free Tier'),
        ('STANDARD', 'Standard'),
        ('PROFESSIONAL', 'Professional'),
        ('ENTERPRISE', 'Enterprise'),
    ]

    code = models.CharField(
        max_length=20, unique=True,
        help_text='Short unique identifier (e.g. ACME, PRETFIT)')
    name = models.CharField(max_length=255)
    slug = models.SlugField(
        max_length=50, unique=True,
        help_text='URL-safe identifier for subdomain/path routing')
    company_type = models.CharField(
        max_length=20, choices=ORG_TYPE_CHOICES, default='FORWARDER',
        help_text='Type of logistics company that owns this platform instance')

    # Contact info
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)

    # Branding (platform-level defaults; company branding overrides these)
    logo = models.ImageField(
        upload_to='org_logos/', blank=True, null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['png', 'jpg', 'jpeg', 'webp'])],
        help_text='Organization logo (recommended: 200x50px PNG with transparent bg)')
    primary_color = models.CharField(
        max_length=7, blank=True, default='#1E2A4A',
        validators=[_hex_color_validator],
        help_text='Primary brand color hex')
    accent_color = models.CharField(
        max_length=7, blank=True, default='#DC3545',
        validators=[_hex_color_validator],
        help_text='Accent/button color hex')
    portal_name = models.CharField(
        max_length=100, blank=True, default='Freight Booking',
        help_text='Platform name shown in navbar for this org')
    favicon = models.ImageField(
        upload_to='org_favicons/', blank=True, null=True,
        help_text='Browser tab icon')

    subscription_tier = models.CharField(
        max_length=20, choices=SUBSCRIPTION_TIER_CHOICES, default='STANDARD')

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['name']
        verbose_name = 'organization'
        verbose_name_plural = 'organizations'


class Customer(models.Model):
    """Company participating in the logistics chain.

    Represents a shipper, consignee, or forwarding partner within an
    Organization's ecosystem. The DB table name remains 'bookings_customer'
    for backward compatibility; a future migration may rename to 'Company'.
    """
    COMPANY_TYPE_CHOICES = [
        ('FORWARDER_ORIGIN', 'Forwarder (Origin)'),
        ('FORWARDER_DEST', 'Forwarder (Destination)'),
        ('SHIPPER', 'Shipper'),
        ('CONSIGNEE', 'Consignee'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='companies',
        help_text='The platform tenant this company belongs to')
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=255)
    company_type = models.CharField(
        max_length=20, choices=COMPANY_TYPE_CHOICES, blank=True, default='',
        help_text='Role in the logistics chain')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Branding / White-label (overrides Organization branding)
    logo = models.ImageField(
        upload_to='customer_logos/', blank=True, null=True,
        validators=[FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp'])],
        help_text='Company logo (recommended: 200x50px PNG with transparent bg)')
    primary_color = models.CharField(
        max_length=7, blank=True, default='',
        validators=[_hex_color_validator],
        help_text='Primary brand color hex, e.g. #1E2A4A')
    accent_color = models.CharField(
        max_length=7, blank=True, default='',
        validators=[_hex_color_validator],
        help_text='Accent/button color hex, e.g. #DC3545')
    portal_name = models.CharField(
        max_length=100, blank=True, default='',
        help_text='Custom portal name shown in navbar')

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_company_code_per_org'),
        ]


class UserProfile(models.Model):
    """Link Django user to an organization and optionally to a company."""
    ROLE_CHOICES = [
        ('USER', 'User'),
        ('SHIPPER', 'Shipper'),
        ('ADMIN', 'Admin'),
        ('OPS', 'Operations'),
    ]

    APPROVAL_STATUS_CHOICES = [
        ('PENDING', 'Pending Approval'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        related_name='user_profiles',
        help_text='Organization this user belongs to')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    additional_customers = models.ManyToManyField(
        Customer, blank=True, related_name='additional_user_profiles',
        help_text='Additional companies this user represents beyond primary')
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
    phone_notifications = models.BooleanField(
        default=False, help_text='Receive SMS notifications for critical events')
    whatsapp_notifications = models.BooleanField(
        default=False, help_text='Receive WhatsApp notifications for critical events')

    def clean(self):
        super().clean()
        if self.pk and self.organization_id:
            wrong_org = self.additional_customers.exclude(
                organization_id=self.organization_id
            ).exists()
            if wrong_org:
                raise ValidationError({
                    'additional_customers':
                    'All additional customers must belong to the same organization.'
                })

    def __str__(self):
        if self.customer:
            return f"{self.user.username} ({self.customer.code})"
        return f"{self.user.username} (Staff)"

    @property
    def is_staff_user(self):
        return self.customer is None and self.organization is not None

    @property
    def is_customer_user(self):
        return self.customer is not None

    @property
    def is_shipper_user(self):
        return self.customer is not None and self.role == 'SHIPPER'

    def get_all_customers(self):
        """Return queryset of primary + additional customers."""
        ids = self.get_all_customer_ids()
        if not ids:
            return Customer.objects.none()
        return Customer.objects.filter(pk__in=ids)

    def get_all_customer_ids(self):
        """Return set of PKs for primary + additional customers."""
        ids = set()
        if self.customer_id:
            ids.add(self.customer_id)
        if self.pk:  # M2M requires saved instance
            ids.update(
                self.additional_customers.values_list('pk', flat=True)
            )
        return ids

    def get_all_company_types(self):
        """Return set of company_type strings from all associated customers."""
        types = set()
        if self.customer_id and self.customer.company_type:
            types.add(self.customer.company_type)
        if self.pk:
            for ct in self.additional_customers.values_list(
                    'company_type', flat=True):
                if ct:
                    types.add(ct)
        return types


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

    PORT_TYPE_CHOICES = [
        ('SEA', 'Sea Port'),
        ('AIR', 'Airport'),
        ('BOTH', 'Sea & Air (Dual-use)'),
    ]

    code = models.CharField(max_length=10, unique=True)  # UN/LOCODE
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    region = models.CharField(max_length=30, choices=REGION_CHOICES, default='NORTH_AMERICA')
    port_type = models.CharField(max_length=4, choices=PORT_TYPE_CHOICES, default='SEA')
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
    capacity_cbm = models.DecimalField(
        max_digits=6, decimal_places=1, null=True, blank=True,
        help_text='Internal cargo capacity in cubic meters'
    )
    max_payload_kg = models.DecimalField(
        max_digits=8, decimal_places=0, null=True, blank=True,
        help_text='Maximum payload weight in kilograms'
    )

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
        ('OPTIONS_PRESENTED', 'Options Presented'),
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
        ('SEA_AIR', 'Sea-Air'),
        ('AIR_SEA', 'Air-Sea'),
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

    SERVICE_TYPE_CHOICES = [
        ('', 'N/A'),
        # Ocean routing strategies
        ('AWS', 'AWS - All Water Service'),
        ('IPI', 'IPI - Interior Point Intermodal'),
        ('MLB', 'MLB - Mini Land Bridge'),
        ('RIPI', 'RIPI - Reverse IPI'),
        # Air service levels
        ('EXPRESS', 'Express'),
        ('STANDARD', 'Standard'),
        ('DEFERRED', 'Deferred'),
    ]

    MOVE_TYPE_CHOICES = [
        ('', 'N/A'),
        ('CY_CY', 'CY-CY (Yard to Yard)'),
        ('CY_CFS', 'CY-CFS (Yard to CFS)'),
        ('CY_SD', 'CY-SD (Yard to Door)'),
        ('CFS_CY', 'CFS-CY (CFS to Yard)'),
        ('CFS_CFS', 'CFS-CFS (CFS to CFS)'),
        ('CFS_SD', 'CFS-SD (CFS to Door)'),
        ('SD_CY', 'SD-CY (Door to Yard)'),
        ('SD_CFS', 'SD-CFS (Door to CFS)'),
        ('SD_SD', 'SD-SD (Door to Door)'),
    ]

    SOURCE_CHANNEL_CHOICES = [
        ('WEB', 'Web Portal'),
        ('API', 'API'),
        ('EDI', 'EDI'),
        ('CSV', 'File Import'),
        ('MANUAL', 'Manual Entry'),
        ('EMAIL', 'Email Intake'),
        ('DOCUMENT', 'Document Import'),
    ]

    # Auto-generated booking number
    booking_number = models.CharField(max_length=20, unique=True, editable=False)

    # Transport mode
    transport_mode = models.CharField(
        max_length=20, choices=TRANSPORT_MODE_CHOICES, default='SEA_FCL',
        help_text='Mode of transport for this shipment'
    )

    # Service type (ocean routing strategy or air service level)
    service_type = models.CharField(
        max_length=10, choices=SERVICE_TYPE_CHOICES,
        blank=True, default='',
        help_text='Routing type for ocean (AWS, IPI, MLB) or service level for air (Express, Standard, Deferred)'
    )

    # Move type (cargo receipt & delivery terms — sea modes only)
    move_type = models.CharField(
        max_length=10, choices=MOVE_TYPE_CHOICES,
        blank=True, default='',
        help_text='Cargo receipt & delivery terms (sea modes only, e.g. CY-CY, CY-SD, SD-SD)'
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

    # Consolidation group (links multiple bookings under one reference)
    consolidation = models.ForeignKey(
        'Consolidation', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bookings',
        help_text='Consolidation group this booking belongs to'
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
        max_length=100, blank=True,
        help_text='Customer or external reference number (required before submission)'
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

    # Workflow version (set at creation, never changed — grandfathering)
    workflow_version = models.ForeignKey(
        'WorkflowTemplateVersion', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='bookings',
        help_text='Workflow version active when this booking was created'
    )

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Notes
    special_instructions = models.TextField(blank=True)

    # HBL generation fields
    freight_terms = models.CharField(
        max_length=20, blank=True,
        choices=[('PREPAID', 'Prepaid'), ('COLLECT', 'Collect'),
                 ('THIRD_PARTY', 'Third Party')],
        help_text='Freight payment terms for Bill of Lading')
    number_of_originals = models.PositiveIntegerField(
        default=3, help_text='Number of original BL copies')

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

    # Carrier options (selected option from the options workflow)
    selected_option = models.ForeignKey(
        'CarrierOption', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='+',
        help_text='Customer-selected carrier option (from options workflow)')

    # Timestamps
    options_presented_at = models.DateTimeField(null=True, blank=True)
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
        allowed = ('SUBMITTED', 'OPTIONS_PRESENTED', 'CONFIRMED', 'PACKING', 'IN_TRANSIT', 'ARRIVED')
        if self.status not in allowed:
            raise ValueError('This booking cannot be rejected.')
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
        if self.status not in ('DRAFT', 'SUBMITTED', 'OPTIONS_PRESENTED', 'CONFIRMED', 'PACKING', 'CUSTOMER_REJECTED'):
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


class CarrierOption(models.Model):
    """A carrier/voyage option presented to a customer for selection."""
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name='carrier_options')
    carrier = models.ForeignKey(
        Carrier, on_delete=models.SET_NULL, null=True, blank=True)
    carrier_name = models.CharField(
        max_length=200, blank=True,
        help_text='Carrier name (auto-filled from carrier FK if set)')
    vessel_name = models.CharField(max_length=200, blank=True)
    voyage_number = models.CharField(max_length=50, blank=True)
    etd = models.DateField(null=True, blank=True, verbose_name='ETD')
    eta = models.DateField(null=True, blank=True, verbose_name='ETA')
    transit_days = models.PositiveIntegerField(null=True, blank=True)
    cost_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text='Quoted cost for this option')
    cost_currency = models.CharField(max_length=3, default='USD')
    notes = models.TextField(blank=True)
    is_selected = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        carrier = self.carrier_name or (self.carrier.name if self.carrier else 'Unknown')
        return f"Option: {carrier} ({self.etd} → {self.eta})"

    def save(self, *args, **kwargs):
        if self.carrier and not self.carrier_name:
            self.carrier_name = self.carrier.name
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['created_at']


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


class Consolidation(models.Model):
    """Groups multiple bookings under one consolidation reference."""
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('CLOSED', 'Closed'),
    ]

    consolidation_number = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='consolidations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='created_consolidations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.consolidation_number} ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        if not self.consolidation_number:
            self.consolidation_number = self._generate_consolidation_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_consolidation_number():
        """Generate CONS-YYYYMM-NNNN (follows booking number pattern)."""
        from django.db import transaction as tx
        today = timezone.now()
        prefix = f"CONS-{today.strftime('%Y%m')}-"
        with tx.atomic():
            last = (
                Consolidation.objects.select_for_update()
                .filter(consolidation_number__startswith=prefix)
                .order_by('-consolidation_number')
                .first()
            )
            if last:
                last_num = int(last.consolidation_number.split('-')[-1])
                new_num = last_num + 1
            else:
                new_num = 1
        return f"{prefix}{new_num:04d}"

    class Meta:
        ordering = ['-created_at']


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
        ('OPTIONS_PRESENTED', 'Carrier Options Presented'),
        ('OPTION_SELECTED', 'Carrier Option Selected'),
        ('CONSOLIDATED', 'Added to Consolidation'),
        ('UNCONSOLIDATED', 'Removed from Consolidation'),
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
        ('BOOKING_OPTIONS_PRESENTED', 'Carrier Options Presented'),
        ('BOOKING_OPTION_SELECTED', 'Carrier Option Selected'),
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


class ImportLog(models.Model):
    """Audit trail for file import sessions."""
    STATUS_CHOICES = [
        ('ANALYZING', 'Analyzing File'),
        ('PREVIEWING', 'Awaiting Confirmation'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]

    import_id = models.UUIDField(unique=True, help_text='Matches session import_id')
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='import_logs',
    )
    customer = models.ForeignKey(
        'Customer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='import_logs',
    )
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(
        null=True, blank=True, help_text='File size in bytes',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ANALYZING')

    extracted_count = models.PositiveIntegerField(default=0)
    valid_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    extraction_notes = models.TextField(blank=True)
    error_message = models.TextField(blank=True, help_text='Error if entire import failed')

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Import {str(self.import_id)[:8]} - {self.filename} ({self.get_status_display()})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'import log'
        verbose_name_plural = 'import logs'


class ImportBookingLog(models.Model):
    """Per-booking detail within an import session."""
    STATUS_CHOICES = [
        ('VALID', 'Valid'),
        ('WARNING', 'Valid with Warnings'),
        ('ERROR', 'Validation Error'),
        ('CREATED', 'Booking Created'),
        ('SKIPPED', 'Not Selected'),
        ('CREATE_FAILED', 'Creation Failed'),
    ]

    import_log = models.ForeignKey(
        ImportLog, on_delete=models.CASCADE, related_name='booking_logs',
    )
    booking = models.ForeignKey(
        'Booking', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='import_booking_logs',
    )
    row_index = models.PositiveIntegerField(help_text='Zero-based index in extraction results')
    row_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='VALID')
    confidence = models.CharField(max_length=20, blank=True, default='medium')

    validation_errors = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)

    was_selected = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        bk = self.booking.booking_number if self.booking else 'N/A'
        return f"Import row {self.row_index} -> {bk} ({self.get_status_display()})"

    class Meta:
        ordering = ['import_log', 'row_index']
        verbose_name = 'import booking log'
        verbose_name_plural = 'import booking logs'


# ─── Workflow Engine models ───────────────────────────────────────────

class WorkflowTemplate(models.Model):
    """Named workflow template belonging to an organization."""
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='workflow_templates')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text='If True, new customers in this org get this workflow automatically')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.organization.code})'

    class Meta:
        ordering = ['organization', 'name']
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'],
                name='unique_workflow_name_per_org'),
        ]


class WorkflowTemplateVersion(models.Model):
    """Immutable snapshot of a workflow template. Bookings reference a specific version."""
    template = models.ForeignKey(
        WorkflowTemplate, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'{self.template.name} v{self.version_number}'

    class Meta:
        ordering = ['template', '-version_number']
        constraints = [
            models.UniqueConstraint(
                fields=['template', 'version_number'],
                name='unique_version_per_template'),
        ]


class WorkflowStep(models.Model):
    """A status that is active in a workflow version, with display order."""
    version = models.ForeignKey(
        WorkflowTemplateVersion, on_delete=models.CASCADE, related_name='steps')
    status = models.CharField(max_length=20, choices=Booking.STATUS_CHOICES)
    order = models.PositiveIntegerField(
        help_text='Display order for this status in the workflow pipeline')
    is_required = models.BooleanField(
        default=True,
        help_text='Must the booking pass through this status?')
    label_override = models.CharField(
        max_length=100, blank=True,
        help_text='Custom label for this status (leave blank for default)')

    def __str__(self):
        label = self.label_override or self.get_status_display()
        return f'{self.version} — {label} (#{self.order})'

    class Meta:
        ordering = ['version', 'order']
        constraints = [
            models.UniqueConstraint(
                fields=['version', 'status'],
                name='unique_status_per_version'),
        ]


class WorkflowTransition(models.Model):
    """An allowed status transition within a workflow version."""
    version = models.ForeignKey(
        WorkflowTemplateVersion, on_delete=models.CASCADE, related_name='transitions')
    from_status = models.CharField(max_length=20, choices=Booking.STATUS_CHOICES)
    to_status = models.CharField(max_length=20, choices=Booking.STATUS_CHOICES)
    required_role = models.CharField(
        max_length=10, choices=UserProfile.ROLE_CHOICES, blank=True,
        help_text='Role required to trigger this transition (blank = any)')
    requires_reason = models.BooleanField(
        default=False,
        help_text='Does this transition require a reason/note?')
    auto_skip = models.BooleanField(
        default=False,
        help_text='Auto-advance through non-required intermediate steps')
    allowed_company_types = models.JSONField(
        default=list, blank=True,
        help_text='Company types that can trigger this transition. '
                  'Empty list = any type (staff or customer). '
                  'Example: ["FORWARDER_ORIGIN", "SHIPPER"]')

    _VALID_COMPANY_TYPES = {c[0] for c in Customer.COMPANY_TYPE_CHOICES}

    def clean(self):
        super().clean()
        if self.allowed_company_types:
            if not isinstance(self.allowed_company_types, list):
                raise ValidationError(
                    {'allowed_company_types': 'Must be a list of company type codes.'})
            for ct in self.allowed_company_types:
                if ct not in self._VALID_COMPANY_TYPES:
                    raise ValidationError(
                        {'allowed_company_types': f'Invalid company type: {ct}'})

    def __str__(self):
        return f'{self.version} — {self.from_status} → {self.to_status}'

    class Meta:
        ordering = ['version', 'from_status', 'to_status']
        constraints = [
            models.UniqueConstraint(
                fields=['version', 'from_status', 'to_status'],
                name='unique_transition_per_version'),
        ]


class CustomerWorkflowConfig(models.Model):
    """Links a customer (company) to a specific workflow version."""
    customer = models.OneToOneField(
        Customer, on_delete=models.CASCADE, related_name='workflow_config')
    workflow_version = models.ForeignKey(
        WorkflowTemplateVersion, on_delete=models.PROTECT,
        related_name='customer_configs')
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'{self.customer.name} → {self.workflow_version}'

    def clean(self):
        # ValidationError imported at module level
        if (self.customer_id and self.workflow_version_id
                and self.customer.organization_id
                != self.workflow_version.template.organization_id):
            raise ValidationError(
                'Customer and workflow version must belong to the same organization.')

    class Meta:
        verbose_name = 'customer workflow config'
        verbose_name_plural = 'customer workflow configs'


# ─── Phase 3: Feature Flags + Field Config ────────────────────────────

class OrganizationFeatureConfig(models.Model):
    """Per-organization feature toggles controlling which modules are available."""
    organization = models.OneToOneField(
        Organization, on_delete=models.CASCADE, related_name='feature_config')
    enable_consolidation = models.BooleanField(
        default=True, help_text='Allow grouping bookings into consolidations')
    enable_import = models.BooleanField(
        default=True, help_text='Allow CSV/Excel/EDI import of bookings')
    enable_parties = models.BooleanField(
        default=True, help_text='Show parties (shipper, consignee, etc.) on bookings')
    enable_documents = models.BooleanField(
        default=True, help_text='Allow document uploads on bookings')
    enable_milestones = models.BooleanField(
        default=True, help_text='Track shipment milestones on bookings')
    enable_customer_approval = models.BooleanField(
        default=True, help_text='Require customer approval step before packing')
    enable_carrier_integration = models.BooleanField(
        default=True, help_text='Enable automated carrier API integrations')
    enable_fms_integration = models.BooleanField(
        default=True, help_text='Enable FMS (freight management system) push')
    enable_templates = models.BooleanField(
        default=True, help_text='Allow saving and reusing booking templates')
    enable_clone = models.BooleanField(
        default=True, help_text='Allow cloning bookings')
    enable_document_review = models.BooleanField(
        default=True, help_text='Enable AI-powered document review for PDFs')
    enable_sanctions_screening = models.BooleanField(
        default=True, help_text='Screen parties against OFAC/EU/UN sanctions lists')
    enable_scheduled_reports = models.BooleanField(
        default=True, help_text='Allow scheduling recurring email reports')
    enable_booking_comments = models.BooleanField(
        default=True, help_text='Enable threaded comments on bookings')
    enable_sla_tracking = models.BooleanField(
        default=True, help_text='Track SLA timers and auto-escalate breaches')
    enable_auto_quoting = models.BooleanField(
        default=True, help_text='Show matching rates when creating bookings')
    enable_phone_notifications = models.BooleanField(
        default=False, help_text='Enable WhatsApp/SMS notifications via Twilio')
    enable_document_to_booking = models.BooleanField(
        default=True, help_text='Create bookings from uploaded PDF documents')
    enable_email_to_booking = models.BooleanField(
        default=False, help_text='Create bookings from inbound emails')
    enable_hbl_generation = models.BooleanField(
        default=True, help_text='Generate draft House Bill of Lading PDFs')
    enable_tracking = models.BooleanField(
        default=False, help_text='Real-time vessel/container tracking via external API')

    def __str__(self):
        return f'Features: {self.organization.name}'

    class Meta:
        verbose_name = 'organization feature config'
        verbose_name_plural = 'organization feature configs'


class FieldConfig(models.Model):
    """Per-customer field visibility and requirements for booking forms.

    The `config` JSONField stores a dict like:
        {
            "commodity_description": {"visible": true, "required": false, "label": "Goods Description"},
            "flight_number": {"visible": false},
            ...
        }
    Staff users always see all fields regardless of this config.
    """
    customer = models.OneToOneField(
        Customer, on_delete=models.CASCADE, related_name='field_config')
    config = models.JSONField(
        default=dict, blank=True,
        help_text='Dict of {field_name: {visible: bool, required: bool, label: str}}')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        field_count = len(self.config) if self.config else 0
        return f'Field config: {self.customer.name} ({field_count} fields)'

    def clean(self):
        # ValidationError imported at module level
        from bookings.feature_service import CONFIGURABLE_FIELDS
        if not isinstance(self.config, dict):
            raise ValidationError({'config': 'Config must be a JSON object.'})
        for field_name, field_cfg in self.config.items():
            if field_name not in CONFIGURABLE_FIELDS:
                raise ValidationError(
                    {'config': f'Unknown field: {field_name!r}.'})
            if not isinstance(field_cfg, dict):
                raise ValidationError(
                    {'config': f'Value for {field_name!r} must be a JSON object.'})
            label = field_cfg.get('label')
            if label is not None and not isinstance(label, str):
                raise ValidationError(
                    {'config': f"'label' for {field_name!r} must be a string."})

    class Meta:
        verbose_name = 'field config'
        verbose_name_plural = 'field configs'


class RateSheet(models.Model):
    """Carrier rate sheet for a specific port pair and date range.

    Linked to carrier, origin/destination ports, validity period, and transport mode.
    Ops staff can reference these rates when creating carrier options for a booking.
    """
    CURRENCY_CHOICES = [
        ('USD', 'USD'),
        ('EUR', 'EUR'),
        ('GBP', 'GBP'),
        ('CNY', 'CNY'),
        ('JPY', 'JPY'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='rate_sheets')
    carrier = models.ForeignKey(
        Carrier, on_delete=models.CASCADE, related_name='rate_sheets')
    origin_port = models.ForeignKey(
        Port, on_delete=models.CASCADE, related_name='rate_sheets_origin')
    destination_port = models.ForeignKey(
        Port, on_delete=models.CASCADE, related_name='rate_sheets_destination')
    transport_mode = models.CharField(
        max_length=10,
        choices=[('SEA', 'Sea'), ('AIR', 'Air'), ('RAIL', 'Rail'), ('ROAD', 'Road')],
        default='SEA')
    container_type = models.ForeignKey(
        ContainerType, on_delete=models.SET_NULL, null=True, blank=True,
        help_text='Applicable container type (for FCL rates)')

    # Rate details
    rate_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text='Rate amount per unit (container, kg, CBM)')
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    rate_basis = models.CharField(
        max_length=20,
        choices=[
            ('PER_CONTAINER', 'Per Container'),
            ('PER_KG', 'Per Kilogram'),
            ('PER_CBM', 'Per Cubic Meter'),
            ('FLAT', 'Flat Rate'),
        ],
        default='PER_CONTAINER',
        help_text='How the rate is measured')
    transit_days = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Expected transit time in days')

    # Validity period
    valid_from = models.DateField(help_text='Rate effective from date')
    valid_to = models.DateField(help_text='Rate effective until date')

    # Metadata
    notes = models.TextField(blank=True, help_text='Additional terms or conditions')
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return (f'{self.carrier.name}: {self.origin_port.code} → '
                f'{self.destination_port.code} ({self.currency} {self.rate_amount})')

    @property
    def is_valid(self):
        """Check if rate is currently within validity period."""
        from datetime import date
        today = date.today()
        return self.is_active and self.valid_from <= today <= self.valid_to

    class Meta:
        ordering = ['-valid_from', 'carrier__name']
        indexes = [
            models.Index(fields=['origin_port', 'destination_port', 'carrier']),
            models.Index(fields=['valid_from', 'valid_to']),
        ]


# ─── Value Enhancement Models ─────────────────────────────────────────

class ScreeningResult(models.Model):
    """Sanctions screening result for a party against OFAC/EU/UN lists."""
    STATUS_CHOICES = [
        ('CLEAR', 'Clear'),
        ('POTENTIAL_MATCH', 'Potential Match'),
        ('BLOCKED', 'Blocked'),
        ('REVIEWED_OK', 'Reviewed - Cleared'),
        ('REVIEWED_BLOCKED', 'Reviewed - Blocked'),
    ]

    party = models.ForeignKey(
        Party, on_delete=models.CASCADE, related_name='screening_results')
    list_checked = models.CharField(max_length=20, help_text='OFAC, EU, or UN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    match_score = models.FloatField(default=0.0, help_text='0.0-1.0 similarity')
    match_details = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.party.company_name} - {self.list_checked}: {self.status}'

    class Meta:
        ordering = ['-checked_at']
        indexes = [models.Index(fields=['party', '-checked_at'])]


class ScheduledReport(models.Model):
    """Scheduled recurring email report configuration."""
    FREQUENCY_CHOICES = [
        ('DAILY', 'Daily'),
        ('WEEKLY', 'Weekly'),
        ('MONTHLY', 'Monthly'),
    ]
    REPORT_TYPE_CHOICES = [
        ('WEEKLY_SUMMARY', 'Weekly Summary'),
        ('MONTHLY_SUMMARY', 'Monthly Summary'),
        ('CARRIER_PERFORMANCE', 'Carrier Performance'),
        ('VOLUME_BY_CUSTOMER', 'Volume by Customer'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='scheduled_reports')
    name = models.CharField(max_length=100)
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    recipients = models.JSONField(
        default=list, help_text='List of email addresses')
    day_of_week = models.IntegerField(
        null=True, blank=True, help_text='0=Monday, 6=Sunday (for weekly)')
    day_of_month = models.IntegerField(
        null=True, blank=True, help_text='1-28 (for monthly)')
    hour = models.IntegerField(default=7, help_text='Hour to send (0-23)')
    last_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.get_frequency_display()})'

    class Meta:
        ordering = ['name']


class BookingComment(models.Model):
    """Threaded comment on a booking for customer<->ops communication."""
    booking = models.ForeignKey(
        'Booking', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField(max_length=5000)
    is_internal = models.BooleanField(
        default=False, help_text='Internal comments visible only to staff')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Comment by {self.author.username} on {self.booking.booking_number}'

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['booking', 'created_at'])]


class SLAConfig(models.Model):
    """SLA timer configuration per status per organization."""
    ESCALATION_CHOICES = [
        ('NOTIFY', 'Send notification'),
        ('FLAG', 'Flag in dashboard'),
        ('BOTH', 'Notify and flag'),
    ]

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='sla_configs')
    status = models.CharField(max_length=30)
    max_hours = models.PositiveIntegerField(
        help_text='Maximum hours allowed in this status')
    warning_pct = models.PositiveIntegerField(
        default=75, help_text='Percentage of max_hours to trigger warning')
    escalation_email = models.EmailField(
        blank=True, help_text='Email to notify on breach')
    escalation_action = models.CharField(
        max_length=10, choices=ESCALATION_CHOICES, default='BOTH')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f'{self.organization.name} - {self.status}: {self.max_hours}h'

    class Meta:
        unique_together = [('organization', 'status')]
        ordering = ['status']


class SLABreach(models.Model):
    """Record of a booking breaching an SLA timer."""
    booking = models.ForeignKey(
        'Booking', on_delete=models.CASCADE, related_name='sla_breaches')
    sla_config = models.ForeignKey(
        SLAConfig, on_delete=models.CASCADE, related_name='breaches')
    status = models.CharField(max_length=30)
    entered_at = models.DateTimeField(help_text='When booking entered this status')
    breached_at = models.DateTimeField(help_text='When the SLA was breached')
    resolved_at = models.DateTimeField(null=True, blank=True)
    escalated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Breach: {self.booking.booking_number} - {self.status}'

    class Meta:
        ordering = ['-breached_at']


class TrackingEvent(models.Model):
    """Vessel/container tracking event from external API or manual entry."""
    SOURCE_CHOICES = [
        ('API', 'External API'),
        ('MANUAL', 'Manual Entry'),
    ]

    booking = models.ForeignKey(
        'Booking', on_delete=models.CASCADE, related_name='tracking_events')
    event_type = models.CharField(max_length=50)
    location = models.CharField(max_length=255, blank=True)
    vessel_name = models.CharField(max_length=100, blank=True)
    occurred_at = models.DateTimeField()
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='API')
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.booking.booking_number} - {self.event_type} at {self.location}'

    class Meta:
        ordering = ['-occurred_at']
        indexes = [models.Index(fields=['booking', '-occurred_at'])]


class VesselPosition(models.Model):
    """Cached vessel position from tracking API."""
    vessel_name = models.CharField(max_length=100)
    imo_number = models.CharField(max_length=20, blank=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    speed_knots = models.FloatField(null=True, blank=True)
    heading = models.FloatField(null=True, blank=True)
    destination = models.CharField(max_length=255, blank=True)
    eta = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.vessel_name} ({self.latitude}, {self.longitude})'

    class Meta:
        indexes = [models.Index(fields=['vessel_name'])]


class InboundEmail(models.Model):
    """Record of an inbound email processed for email-to-booking."""
    STATUS_CHOICES = [
        ('RECEIVED', 'Received'),
        ('PROCESSED', 'Processed'),
        ('FAILED', 'Failed'),
    ]

    sender = models.EmailField()
    subject = models.CharField(max_length=500)
    body = models.TextField()
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey(
        'Booking', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='source_emails')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='RECEIVED')
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.sender}: {self.subject[:50]}'

    class Meta:
        ordering = ['-created_at']
