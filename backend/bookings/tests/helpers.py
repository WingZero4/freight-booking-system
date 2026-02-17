"""
Test data factory for the freight booking system.

Provides functions to create minimal valid objects with sensible defaults,
so tests only need to specify what they care about.
"""
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from bookings.models import (
    Customer, UserProfile, Port, ContainerType,
    Booking, BookingItem, BookingDocument, Party, BookingParty,
    ShipmentMilestone,
)


def create_customer(code='CUST01', name='Test Customer', **kwargs):
    defaults = {
        'email': f'{code.lower()}@example.com',
        'phone': '+1-555-0100',
        'country': 'US',
        'is_active': True,
    }
    defaults.update(kwargs)
    return Customer.objects.create(code=code, name=name, **defaults)


def create_user(username='testuser', is_staff=False, customer=None, role='USER', **kwargs):
    """Create a User + UserProfile. Returns the User instance."""
    password = kwargs.pop('password', 'testpass123')
    email = kwargs.pop('email', f'{username}@example.com')
    user = User.objects.create_user(
        username=username, password=password, email=email,
        is_staff=is_staff, **kwargs
    )
    UserProfile.objects.create(user=user, customer=customer, role=role)
    return user


def create_port(code='USNYC', name='New York', country='US', **kwargs):
    defaults = {'is_active': True}
    defaults.update(kwargs)
    return Port.objects.create(code=code, name=name, country=country, **defaults)


def create_container_type(code='20GP', name="20' General Purpose", size_ft=20):
    return ContainerType.objects.create(code=code, name=name, size_ft=size_ft)


def create_booking(customer, user, status='DRAFT', **kwargs):
    """Create a Booking with required FK objects auto-created if not provided."""
    defaults = {
        'transport_mode': 'SEA_FCL',
        'cargo_ready_date': date.today() + timedelta(days=14),
        'container_count': 1,
        'incoterms': 'FOB',
        'source_channel': 'WEB',
        'external_reference': 'TEST-REF-001',
    }
    defaults.update(kwargs)

    # Auto-create origin/destination ports if not given
    if 'origin_port' not in defaults:
        defaults['origin_port'] = Port.objects.filter(code='USNYC').first() or create_port()
    if 'destination_port' not in defaults:
        defaults['destination_port'] = Port.objects.filter(code='CNSHA').first() or create_port(
            code='CNSHA', name='Shanghai', country='CN'
        )
    if 'container_type' not in defaults:
        defaults['container_type'] = ContainerType.objects.first() or create_container_type()

    booking = Booking(
        customer=customer,
        created_by=user,
        status=status,
        **defaults,
    )
    booking.save()
    return booking


def create_booking_item(booking, description='Test Cargo', **kwargs):
    defaults = {
        'package_type': 'CARTON',
        'quantity': 10,
        'weight_kg': Decimal('100.00'),
    }
    defaults.update(kwargs)
    return BookingItem.objects.create(booking=booking, description=description, **defaults)


def create_party(customer, role='SHIPPER', company_name='Test Shipper Co', **kwargs):
    defaults = {
        'contact_name': 'John Doe',
        'email': 'john@example.com',
        'phone': '+1-555-0200',
        'country_code': 'US',
        'is_active': True,
    }
    defaults.update(kwargs)
    return Party.objects.create(
        customer=customer, role=role, company_name=company_name, **defaults
    )


def create_document(booking, user, doc_type='OTHER', filename='test_doc.pdf', **kwargs):
    """Create a BookingDocument with a fake file."""
    file_content = b'%PDF-1.4 fake content'
    uploaded_file = SimpleUploadedFile(filename, file_content, content_type='application/pdf')
    defaults = {
        'original_filename': filename,
        'file_size': len(file_content),
        'notes': '',
    }
    defaults.update(kwargs)
    return BookingDocument.objects.create(
        booking=booking,
        document_type=doc_type,
        file=uploaded_file,
        uploaded_by=user,
        **defaults,
    )


def create_milestone(booking, milestone_type='CARGO_RECEIVED', occurred_at=None,
                     user=None, **kwargs):
    """Create a ShipmentMilestone with sensible defaults."""
    from django.utils import timezone
    defaults = {
        'location': '',
        'notes': '',
    }
    defaults.update(kwargs)
    return ShipmentMilestone.objects.create(
        booking=booking,
        milestone_type=milestone_type,
        occurred_at=occurred_at or timezone.now(),
        recorded_by=user,
        **defaults,
    )
