from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from bookings.models import Customer, UserProfile, Port, ContainerType, Booking, BookingItem
from datetime import date, timedelta


class Command(BaseCommand):
    help = 'Load sample data for MVP demo'

    def handle(self, *args, **options):
        self.stdout.write('Loading sample data...')

        # Create ports
        ports_data = [
            ('CNSHA', 'Shanghai', 'China'),
            ('CNSHE', 'Shenzhen', 'China'),
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

        # Create sample bookings
        if not Booking.objects.exists():
            shanghai = Port.objects.get(code='CNSHA')
            la = Port.objects.get(code='USLAX')
            hc40 = ContainerType.objects.get(code='40HC')

            # Draft booking
            b1 = Booking.objects.create(
                customer=acme,
                created_by=customer_user,
                origin_port=shanghai,
                destination_port=la,
                cargo_ready_date=date.today() + timedelta(days=14),
                container_type=hc40,
                container_count=2,
                status='DRAFT',
                special_instructions='Handle with care - fragile electronics'
            )
            BookingItem.objects.create(
                booking=b1,
                description='LCD Monitors',
                package_type='PALLET',
                quantity=50,
                weight_kg=2500
            )

            # Submitted booking
            b2 = Booking.objects.create(
                customer=acme,
                created_by=customer_user,
                origin_port=shanghai,
                destination_port=la,
                cargo_ready_date=date.today() + timedelta(days=7),
                container_type=hc40,
                container_count=1,
                status='SUBMITTED',
                special_instructions='Temperature sensitive'
            )
            b2.submit()
            BookingItem.objects.create(
                booking=b2,
                description='Computer Components',
                package_type='CARTON',
                quantity=200,
                weight_kg=1800
            )

            self.stdout.write('  Created 2 sample bookings')

        self.stdout.write(self.style.SUCCESS('Sample data loaded successfully!'))
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        self.stdout.write('  Admin:    admin / admin123')
        self.stdout.write('  Customer: acme_user / demo123')
