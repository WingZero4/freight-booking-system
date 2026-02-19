import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0026_add_organization_model'),
    ]

    operations = [
        # Add company_type to Customer
        migrations.AddField(
            model_name='customer',
            name='company_type',
            field=models.CharField(
                blank=True, default='',
                choices=[
                    ('FORWARDER_ORIGIN', 'Forwarder (Origin)'),
                    ('FORWARDER_DEST', 'Forwarder (Destination)'),
                    ('SHIPPER', 'Shipper'),
                    ('CONSIGNEE', 'Consignee'),
                ],
                help_text='Role in the logistics chain', max_length=20),
        ),
        # Add nullable organization FK to Customer
        migrations.AddField(
            model_name='customer',
            name='organization',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='The platform tenant this company belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='companies',
                to='bookings.organization'),
        ),
        # Add nullable organization FK to UserProfile
        migrations.AddField(
            model_name='userprofile',
            name='organization',
            field=models.ForeignKey(
                blank=True, null=True,
                help_text='Organization this user belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='user_profiles',
                to='bookings.organization'),
        ),
    ]
