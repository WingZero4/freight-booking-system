from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from bookings.models import (
    Customer, UserProfile, Port, ContainerType,
    Booking, BookingItem, Party, BookingParty,
)
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Load sample data for MVP demo (only runs when DEBUG=True)'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            self.stderr.write(self.style.ERROR(
                'WARNING: This command creates demo users with weak passwords. '
                'It should only be run with DEBUG=True. Aborting.'
            ))
            return

        self.stdout.write('Loading sample data...')

        # Create ports
        ports_data = [
            ('CNSHA', 'Shanghai', 'China'),
            ('CNSZX', 'Shenzhen', 'China'),
            ('CNNGB', 'Ningbo', 'China'),
            ('USLAX', 'Los Angeles', 'United States'),
            ('USNYC', 'New York', 'United States'),
            ('NLRTM', 'Rotterdam', 'Netherlands'),
            ('DEHAM', 'Hamburg', 'Germany'),
            ('SGSIN', 'Singapore', 'Singapore'),
        ]
        for code, name, country in ports_data:
            Port.objects.get_or_create(code=code, defaults={'name': name, 'country': country})
        self.stdout.write(f'  Created {len(ports_data)} ports')

        # Create container types
        containers_data = [
            ('20GP', "20' General Purpose", 20),
            ('40GP', "40' General Purpose", 40),
            ('40HC', "40' High Cube", 40),
            ('20RF', "20' Reefer", 20),
            ('40RF', "40' Reefer", 40),
        ]
        for code, name, size in containers_data:
            ContainerType.objects.get_or_create(code=code, defaults={'name': name, 'size_ft': size})
        self.stdout.write(f'  Created {len(containers_data)} container types')

        # Create customers
        customers_data = [
            ('ACME', 'Acme Electronics Ltd', 'acme@example.com', 'Shanghai', 'China'),
            ('GLOBEX', 'Globex Trading Co', 'globex@example.com', 'Hong Kong', 'China'),
            ('INITECH', 'Initech Manufacturing', 'initech@example.com', 'Shenzhen', 'China'),
        ]
        for code, name, email, city, country in customers_data:
            Customer.objects.get_or_create(code=code, defaults={
                'name': name, 'email': email, 'city': city, 'country': country
            })
        self.stdout.write(f'  Created {len(customers_data)} customers')

        # Create admin user if not exists
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@example.com', 'is_staff': True, 'is_superuser': True}
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            UserProfile.objects.create(user=admin_user, role='ADMIN')
            self.stdout.write('  Created admin user (admin/admin123)')

        # Create customer users
        acme = Customer.objects.get(code='ACME')
        customer_user, created = User.objects.get_or_create(
            username='acme_user',
            defaults={'email': 'user@acme.com', 'first_name': 'John', 'last_name': 'Smith'}
        )
        if created:
            customer_user.set_password('demo123')
            customer_user.save()
            UserProfile.objects.create(user=customer_user, customer=acme, role='USER')
            self.stdout.write('  Created customer user (acme_user/demo123)')

        # Create address book parties (Phase 1.5)
        if not Party.objects.filter(customer=acme).exists():
            Party.objects.create(
                customer=acme,
                role='SHIPPER',
                company_name='Acme Electronics Ltd',
                contact_name='Wang Wei',
                email='shipping@acme-electronics.com',
                phone='+86-21-5555-0100',
                address_line_1='88 Pudong Avenue',
                city='Shanghai',
                state='Shanghai',
                postal_code='200120',
                country_code='CN',
                tax_id='91310000MA1FL8XQ30',
                is_default=True,
            )
            Party.objects.create(
                customer=acme,
                role='CONSIGNEE',
                company_name='TechMart Distribution Inc',
                contact_name='Mike Johnson',
                email='receiving@techmart.com',
                phone='+1-310-555-0200',
                address_line_1='1200 Harbor Blvd',
                address_line_2='Suite 400',
                city='Los Angeles',
                state='CA',
                postal_code='90731',
                country_code='US',
                tax_id='95-4567890',
                is_default=True,
            )
            Party.objects.create(
                customer=acme,
                role='NOTIFY',
                company_name='Pacific Customs Brokers',
                contact_name='Sarah Chen',
                email='clearance@pacificbrokers.com',
                phone='+1-310-555-0300',
                address_line_1='500 World Trade Center',
                city='Long Beach',
                state='CA',
                postal_code='90802',
                country_code='US',
                is_default=True,
            )
            self.stdout.write('  Created 3 address book parties for ACME')

        # Create sample bookings
        if not Booking.objects.exists():
            shanghai = Port.objects.get(code='CNSHA')
            la = Port.objects.get(code='USLAX')
            hc40 = ContainerType.objects.get(code='40HC')

            # Draft booking with INCOTERMS and parties
            b1 = Booking.objects.create(
                customer=acme,
                created_by=customer_user,
                origin_port=shanghai,
                destination_port=la,
                cargo_ready_date=date.today() + timedelta(days=14),
                container_type=hc40,
                container_count=2,
                status='DRAFT',
                incoterms='FOB',
                incoterms_location='Shanghai Port',
                commodity_description='Electronic displays and components',
                special_instructions='Handle with care - fragile electronics',
            )
            BookingItem.objects.create(
                booking=b1,
                description='LCD Monitors',
                package_type='PALLET',
                quantity=50,
                weight_kg=2500,
                hs_code='852872',
                country_of_origin='CN',
            )

            # Assign parties to draft booking
            shipper = Party.objects.filter(customer=acme, role='SHIPPER').first()
            consignee = Party.objects.filter(customer=acme, role='CONSIGNEE').first()
            notify = Party.objects.filter(customer=acme, role='NOTIFY').first()
            if shipper:
                BookingParty.create_from_party(b1, shipper)
            if consignee:
                BookingParty.create_from_party(b1, consignee)
            if notify:
                BookingParty.create_from_party(b1, notify)

            # Submitted booking
            b2 = Booking.objects.create(
                customer=acme,
                created_by=customer_user,
                origin_port=shanghai,
                destination_port=la,
                cargo_ready_date=date.today() + timedelta(days=7),
                container_type=hc40,
                container_count=1,
                status='DRAFT',
                incoterms='CIF',
                incoterms_location='Los Angeles',
                commodity_description='Computer hardware',
                special_instructions='Temperature sensitive',
            )
            BookingItem.objects.create(
                booking=b2,
                description='Computer Components',
                package_type='CARTON',
                quantity=200,
                weight_kg=1800,
                hs_code='847130',
                country_of_origin='CN',
            )
            b2.submit()

            self.stdout.write('  Created 2 sample bookings with parties')

        self.stdout.write(self.style.SUCCESS('Sample data loaded successfully!'))
        self.stdout.write('')
        self.stdout.write(self.style.WARNING('DEMO CREDENTIALS (change in production):'))
        self.stdout.write('  Admin:    admin / admin123')
        self.stdout.write('  Customer: acme_user / demo123')
