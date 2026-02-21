"""Management command to download and update sanctions screening lists."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Download and update OFAC/EU/UN sanctions lists for party screening'

    def handle(self, *args, **options):
        from bookings.screening_service import update_sanctions_data

        self.stdout.write('Updating sanctions lists...')
        try:
            result = update_sanctions_data()
            self.stdout.write(self.style.SUCCESS(
                f'Sanctions lists updated: {result}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {e}'))
