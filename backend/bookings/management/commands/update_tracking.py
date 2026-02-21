"""Management command to refresh vessel/container tracking data."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Refresh vessel and container tracking data for active bookings'

    def handle(self, *args, **options):
        from bookings.tracking_service import bulk_update_tracking

        self.stdout.write('Updating tracking data...')
        updated, errors = bulk_update_tracking()
        self.stdout.write(self.style.SUCCESS(f'Bookings updated: {updated}'))
        if errors:
            for err in errors:
                self.stdout.write(self.style.WARNING(f'  Error: {err}'))
