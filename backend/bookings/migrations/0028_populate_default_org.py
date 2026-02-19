from django.db import migrations


def forwards(apps, schema_editor):
    """Create default Organization and assign all existing records."""
    Organization = apps.get_model('bookings', 'Organization')
    Customer = apps.get_model('bookings', 'Customer')
    UserProfile = apps.get_model('bookings', 'UserProfile')

    # Create the default organization
    org = Organization.objects.create(
        code='DEFAULT',
        name='Freight Forwarding Co.',
        slug='default',
        company_type='FORWARDER',
        email='',
        portal_name='Freight Booking',
        primary_color='#1E2A4A',
        accent_color='#DC3545',
        is_active=True,
    )

    # Assign all existing customers to the default org
    Customer.objects.filter(organization__isnull=True).update(organization=org)

    # Assign all existing user profiles to the default org
    UserProfile.objects.filter(organization__isnull=True).update(organization=org)

    # Map old roles: OPERATIONS -> OPS, SALES -> USER
    UserProfile.objects.filter(role='OPERATIONS').update(role='OPS')
    UserProfile.objects.filter(role='SALES').update(role='USER')


def backwards(apps, schema_editor):
    """Reverse: clear org FKs, restore role values, delete default org."""
    Customer = apps.get_model('bookings', 'Customer')
    UserProfile = apps.get_model('bookings', 'UserProfile')
    Organization = apps.get_model('bookings', 'Organization')

    # Restore old roles
    UserProfile.objects.filter(role='OPS').update(role='OPERATIONS')

    # Clear FKs
    Customer.objects.all().update(organization=None)
    UserProfile.objects.all().update(organization=None)

    # Delete default org
    Organization.objects.filter(code='DEFAULT').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0027_add_company_type_org_fk'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
