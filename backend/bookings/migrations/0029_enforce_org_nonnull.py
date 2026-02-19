import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0028_populate_default_org'),
    ]

    operations = [
        # Remove the old unique constraint on Customer.code
        migrations.AlterField(
            model_name='customer',
            name='code',
            field=models.CharField(max_length=20),
        ),
        # Make Customer.organization non-nullable
        migrations.AlterField(
            model_name='customer',
            name='organization',
            field=models.ForeignKey(
                help_text='The platform tenant this company belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='companies',
                to='bookings.organization'),
        ),
        # Make UserProfile.organization non-nullable
        migrations.AlterField(
            model_name='userprofile',
            name='organization',
            field=models.ForeignKey(
                help_text='Organization this user belongs to',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='user_profiles',
                to='bookings.organization'),
        ),
        # Add unique constraint: code unique within org
        migrations.AddConstraint(
            model_name='customer',
            constraint=models.UniqueConstraint(
                fields=['organization', 'code'],
                name='unique_company_code_per_org'),
        ),
        # Update UserProfile role choices
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(
                choices=[
                    ('USER', 'User'),
                    ('ADMIN', 'Admin'),
                    ('OPS', 'Operations'),
                ],
                default='USER', max_length=20),
        ),
    ]
