import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0025_add_move_type_and_consolidation'),
    ]

    operations = [
        migrations.CreateModel(
            name='Organization',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(help_text='Short unique identifier (e.g. ACME, PRETFIT)', max_length=20, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('slug', models.SlugField(help_text='URL-safe identifier for subdomain/path routing', unique=True)),
                ('company_type', models.CharField(
                    choices=[
                        ('FORWARDER', 'Freight Forwarder'),
                        ('SHIPPER', 'Shipper'),
                        ('CONSIGNEE', 'Consignee'),
                        ('RETAILER', 'Retailer / Buyer'),
                        ('OTHER', 'Other'),
                    ],
                    default='FORWARDER', help_text='Type of logistics company that owns this platform instance', max_length=20)),
                ('email', models.EmailField(blank=True, max_length=254)),
                ('phone', models.CharField(blank=True, max_length=50)),
                ('address', models.TextField(blank=True)),
                ('city', models.CharField(blank=True, max_length=100)),
                ('country', models.CharField(blank=True, max_length=100)),
                ('website', models.URLField(blank=True)),
                ('logo', models.ImageField(
                    blank=True, null=True, upload_to='org_logos/',
                    validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg', 'webp'])],
                    help_text='Organization logo (recommended: 200x50px PNG with transparent bg)')),
                ('primary_color', models.CharField(
                    blank=True, default='#1E2A4A', max_length=7,
                    validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Enter a valid hex color code (e.g. #1E2A4A).')],
                    help_text='Primary brand color hex')),
                ('accent_color', models.CharField(
                    blank=True, default='#DC3545', max_length=7,
                    validators=[django.core.validators.RegexValidator('^#[0-9A-Fa-f]{6}$', 'Enter a valid hex color code (e.g. #1E2A4A).')],
                    help_text='Accent/button color hex')),
                ('portal_name', models.CharField(blank=True, default='Freight Booking', help_text='Platform name shown in navbar for this org', max_length=100)),
                ('favicon', models.ImageField(blank=True, null=True, upload_to='org_favicons/', help_text='Browser tab icon')),
                ('subscription_tier', models.CharField(
                    choices=[
                        ('FREE', 'Free Tier'),
                        ('STANDARD', 'Standard'),
                        ('PROFESSIONAL', 'Professional'),
                        ('ENTERPRISE', 'Enterprise'),
                    ],
                    default='STANDARD', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'organization',
                'verbose_name_plural': 'organizations',
                'ordering': ['name'],
            },
        ),
    ]
