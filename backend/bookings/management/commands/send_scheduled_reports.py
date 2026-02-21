"""Management command to check and send due scheduled reports."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Check and send any scheduled reports that are due'

    def handle(self, *args, **options):
        from bookings.report_scheduler import send_scheduled_reports

        self.stdout.write('Checking scheduled reports...')
        sent, errors = send_scheduled_reports()
        self.stdout.write(self.style.SUCCESS(f'Reports sent: {sent}'))
        if errors:
            for err in errors:
                self.stdout.write(self.style.WARNING(f'  Error: {err}'))
