from django.core.management.base import BaseCommand
from django.contrib.auth.models import User

from bookings.models import Customer, UserProfile, Organization


# Test user definitions: (username, password, company_type, role, is_staff)
TEST_USERS = [
    {
        'username': 'test_forwarder_origin',
        'password': 'TestFwd0rigin2026!',
        'company_type': 'FORWARDER_ORIGIN',
        'company_name': 'Test Origin Forwarder Co.',
        'company_code': 'TFWD_O',
        'role': 'USER',
        'is_staff': False,
    },
    {
        'username': 'test_forwarder_dest',
        'password': 'TestFwdDest2026!',
        'company_type': 'FORWARDER_DEST',
        'company_name': 'Test Destination Forwarder Co.',
        'company_code': 'TFWD_D',
        'role': 'USER',
        'is_staff': False,
    },
    {
        'username': 'test_shipper',
        'password': 'TestShipper2026!',
        'company_type': 'SHIPPER',
        'company_name': 'Test Shipper Inc.',
        'company_code': 'TSHIP',
        'role': 'SHIPPER',
        'is_staff': False,
    },
    {
        'username': 'test_consignee',
        'password': 'TestConsignee2026!',
        'company_type': 'CONSIGNEE',
        'company_name': 'Test Consignee Ltd.',
        'company_code': 'TCONS',
        'role': 'USER',
        'is_staff': False,
    },
    {
        'username': 'test_ops',
        'password': 'TestOps2026!',
        'company_type': '',
        'company_name': '',
        'company_code': '',
        'role': 'OPS',
        'is_staff': True,
    },
]


class Command(BaseCommand):
    help = 'Create test user accounts for each company type (idempotent, DEBUG only)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Run even when DEBUG is False (not recommended for production)')

    def handle(self, *args, **options):
        from django.conf import settings
        if not settings.DEBUG and not options['force']:
            self.stderr.write(self.style.ERROR(
                'REFUSED: This command creates users with known passwords. '
                'Only run with DEBUG=True or use --force.'))
            return
        # Get or create the default organization
        org = Organization.objects.first()
        if not org:
            org = Organization.objects.create(
                name='Default Organization',
                slug='default',
            )
            self.stdout.write(self.style.WARNING(
                f'  Created default organization: {org.name}'))

        self.stdout.write(f'Using organization: {org.name}\n')

        for entry in TEST_USERS:
            username = entry['username']
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@test.example.com',
                    'is_staff': entry['is_staff'],
                    'first_name': username.replace('_', ' ').title(),
                },
            )
            if created:
                user.set_password(entry['password'])
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'  Created user: {username}'))
            else:
                self.stdout.write(f'  User already exists: {username}')

            # Create customer record if this is a customer user
            customer = None
            if entry['company_code']:
                customer, c_created = Customer.objects.get_or_create(
                    organization=org,
                    code=entry['company_code'],
                    defaults={
                        'name': entry['company_name'],
                        'company_type': entry['company_type'],
                        'email': f'{username}@test.example.com',
                    },
                )
                if c_created:
                    self.stdout.write(self.style.SUCCESS(
                        f'    Created company: {customer.code} '
                        f'({customer.company_type})'))

            # Create or update user profile
            profile, p_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'organization': org,
                    'customer': customer,
                    'role': entry['role'],
                    'approval_status': 'APPROVED',
                },
            )
            if p_created:
                self.stdout.write(f'    Created profile: role={profile.role}')
            elif profile.customer != customer or profile.role != entry['role']:
                profile.customer = customer
                profile.role = entry['role']
                profile.organization = org
                profile.save()
                self.stdout.write(f'    Updated profile: role={profile.role}')

        # Create multi-customer test user (FORWARDER_ORIGIN + FORWARDER_DEST)
        mc_username = 'test_multi_customer'
        mc_password = 'TestMulti2026!'
        mc_user, mc_created = User.objects.get_or_create(
            username=mc_username,
            defaults={
                'email': f'{mc_username}@test.example.com',
                'is_staff': False,
                'first_name': 'Test Multi Customer',
            },
        )
        if mc_created:
            mc_user.set_password(mc_password)
            mc_user.save()
            self.stdout.write(self.style.SUCCESS(
                f'  Created user: {mc_username}'))
        else:
            self.stdout.write(f'  User already exists: {mc_username}')

        # Primary = TFWD_O, additional = TFWD_D
        primary_co = Customer.objects.filter(
            organization=org, code='TFWD_O').first()
        additional_co = Customer.objects.filter(
            organization=org, code='TFWD_D').first()

        if primary_co:
            mc_profile, mcp_created = UserProfile.objects.get_or_create(
                user=mc_user,
                defaults={
                    'organization': org,
                    'customer': primary_co,
                    'role': 'USER',
                    'approval_status': 'APPROVED',
                },
            )
            if mcp_created:
                self.stdout.write(
                    f'    Created profile: primary={primary_co.code}')
            if additional_co:
                mc_profile.additional_customers.add(additional_co)
                self.stdout.write(
                    f'    Added additional customer: {additional_co.code}')

        # Print summary table
        self.stdout.write('\n' + '=' * 70)
        self.stdout.write('Test User Credentials:')
        self.stdout.write('=' * 70)
        self.stdout.write(
            f'{"Username":<25} {"Password":<22} {"Type":<20} {"Staff"}')
        self.stdout.write('-' * 70)
        for entry in TEST_USERS:
            self.stdout.write(
                f'{entry["username"]:<25} '
                f'{entry["password"]:<22} '
                f'{entry["company_type"] or "Staff/OPS":<20} '
                f'{"Yes" if entry["is_staff"] else "No"}')
        self.stdout.write(
            f'{"test_multi_customer":<25} '
            f'{"TestMulti2026!":<22} '
            f'{"MULTI (O+D)":<20} '
            f'No')
        self.stdout.write('=' * 70)
        self.stdout.write(self.style.SUCCESS('\nDone! All test users ready.'))
