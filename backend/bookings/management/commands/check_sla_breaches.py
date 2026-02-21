"""Management command to scan for SLA breaches and escalate."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Scan active bookings for SLA breaches and send escalation notifications'

    def handle(self, *args, **options):
        from bookings.sla_service import check_sla_breaches

        self.stdout.write('Checking SLA breaches...')
        breaches, errors = check_sla_breaches()
        self.stdout.write(self.style.SUCCESS(f'New breaches found: {breaches}'))
        if errors:
            for err in errors:
                self.stdout.write(self.style.WARNING(f'  Error: {err}'))
