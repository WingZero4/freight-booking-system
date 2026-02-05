from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


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

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['name']


class UserProfile(models.Model):
    """Link Django user to customer"""
    ROLE_CHOICES = [
        ('ADMIN', 'Admin'),
        ('USER', 'User'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='USER')
    phone = models.CharField(max_length=50, blank=True)

    def __str__(self):
        if self.customer:
            return f"{self.user.username} ({self.customer.code})"
        return f"{self.user.username} (Staff)"

    @property
    def is_staff_user(self):
        return self.customer is None


class Port(models.Model):
    """Seaports"""
    code = models.CharField(max_length=10, unique=True)  # UN/LOCODE
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['code']


class ContainerType(models.Model):
    """Container specifications"""
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=50)
    size_ft = models.IntegerField()

    def __str__(self):
        return f"{self.code} ({self.name})"

    class Meta:
        ordering = ['size_ft', 'code']


class Booking(models.Model):
    """Ocean FCL Booking"""
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted'),
        ('CONFIRMED', 'Confirmed'),
        ('CANCELLED', 'Cancelled'),
    ]

    # Auto-generated booking number
    booking_number = models.CharField(max_length=20, unique=True, editable=False)

    # Customer
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    # Route
    origin_port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name='origin_bookings')
    destination_port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name='destination_bookings')

    # Dates
    cargo_ready_date = models.DateField()

    # Container
    container_type = models.ForeignKey(ContainerType, on_delete=models.PROTECT)
    container_count = models.PositiveIntegerField(default=1)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')

    # Notes
    special_instructions = models.TextField(blank=True)

    # Carrier info (filled by operations)
    carrier_name = models.CharField(max_length=100, blank=True)
    vessel_name = models.CharField(max_length=100, blank=True)
    voyage_number = models.CharField(max_length=50, blank=True)
    etd = models.DateField(null=True, blank=True, verbose_name="ETD")
    eta = models.DateField(null=True, blank=True, verbose_name="ETA")

    # Timestamps
    submitted_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.booking_number} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.booking_number:
            self.booking_number = self._generate_booking_number()
        super().save(*args, **kwargs)

    def _generate_booking_number(self):
        """Generate booking number: BK-YYYYMM-NNNN"""
        today = timezone.now()
        prefix = f"BK-{today.strftime('%Y%m')}-"

        # Get last booking this month
        last = Booking.objects.filter(
            booking_number__startswith=prefix
        ).order_by('-booking_number').first()

        if last:
            last_num = int(last.booking_number.split('-')[-1])
            new_num = last_num + 1
        else:
            new_num = 1

        return f"{prefix}{new_num:04d}"

    def submit(self):
        """Submit booking for processing"""
        if self.status == 'DRAFT':
            self.status = 'SUBMITTED'
            self.submitted_at = timezone.now()
            self.save()

    def confirm(self):
        """Confirm booking (operations action)"""
        if self.status == 'SUBMITTED':
            self.status = 'CONFIRMED'
            self.confirmed_at = timezone.now()
            self.save()

    def cancel(self):
        """Cancel booking"""
        if self.status in ['DRAFT', 'SUBMITTED']:
            self.status = 'CANCELLED'
            self.save()

    class Meta:
        ordering = ['-created_at']


class BookingItem(models.Model):
    """Cargo items in a booking"""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=500)
    package_type = models.CharField(max_length=50, blank=True)  # PALLET, CARTON, etc.
    quantity = models.PositiveIntegerField()
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity}x {self.description} ({self.weight_kg}kg)"

    class Meta:
        ordering = ['id']
