"""
Background worker for stuck dispatch recovery and webhook retries.

Runs as a PythonAnywhere always-on task. Each cycle:
1. Recovers stuck FMS dispatches (status=PENDING for too long)
2. Recovers stuck carrier dispatches (same pattern)
3. Processes pending webhook retries

Usage:
    python manage.py run_worker              # continuous loop (default 30s)
    python manage.py run_worker --interval 60
    python manage.py run_worker --once       # single cycle, then exit
"""
import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run background worker for dispatch recovery and webhook retries'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._shutdown = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval', type=int, default=30,
            help='Seconds between worker cycles (default: 30)',
        )
        parser.add_argument(
            '--stuck-threshold', type=int, default=300,
            help='Seconds before a PENDING dispatch is considered stuck (default: 300)',
        )
        parser.add_argument(
            '--once', action='store_true',
            help='Run a single cycle then exit (for testing)',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        stuck_threshold = options['stuck_threshold']
        once = options['once']

        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        self.stdout.write(self.style.SUCCESS(
            f'Worker started (interval={interval}s, stuck_threshold={stuck_threshold}s)'
        ))

        while not self._shutdown:
            try:
                self._run_cycle(stuck_threshold)
            except Exception:
                logger.exception('Worker cycle failed')
            finally:
                close_old_connections()

            if once:
                self.stdout.write('Single cycle complete — exiting.')
                break

            # Sleep in 1-second increments so we can respond to SIGTERM quickly
            for _ in range(interval):
                if self._shutdown:
                    break
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS('Worker stopped gracefully.'))

    def _handle_signal(self, signum, frame):
        sig_name = signal.Signals(signum).name
        self.stdout.write(f'Received {sig_name} — shutting down after current cycle.')
        self._shutdown = True

    def _run_cycle(self, stuck_threshold):
        """Execute one worker cycle: recover stuck dispatches + process retries."""
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(seconds=stuck_threshold)

        fms_count = self._recover_stuck_fms(cutoff)
        carrier_count = self._recover_stuck_carrier(cutoff)
        retry_count = self._process_webhook_retries()

        if fms_count or carrier_count or retry_count:
            self.stdout.write(
                f'Cycle: FMS={fms_count}, carrier={carrier_count}, '
                f'webhook_retries={retry_count}'
            )

    def _recover_stuck_fms(self, cutoff):
        """Re-dispatch bookings stuck in fms_push_status=PENDING.

        Uses atomic conditional update to prevent race with daemon threads.
        """
        from bookings.models import Booking
        from integrations import dispatch as fms_dispatch

        stuck_pks = list(
            Booking.objects.filter(
                fms_push_status='PENDING',
                updated_at__lt=cutoff,
            ).values_list('pk', flat=True)[:20]
        )

        count = 0
        for pk in stuck_pks:
            try:
                booking = Booking.objects.get(pk=pk)
                # Re-check status — may have been resolved by the original thread
                if booking.fms_push_status != 'PENDING':
                    continue
                logger.info(
                    'Recovering stuck FMS dispatch for %s',
                    booking.booking_number,
                )
                fms_dispatch.dispatch_booking_confirmed(booking)
                count += 1
            except Booking.DoesNotExist:
                continue
            except Exception:
                logger.exception(
                    'Failed to recover FMS dispatch for booking pk=%s', pk,
                )

        return count

    def _recover_stuck_carrier(self, cutoff):
        """Re-dispatch bookings stuck in carrier_request_status=PENDING.

        Uses atomic conditional update to prevent race with daemon threads.
        """
        from bookings.models import Booking
        from integrations import carrier_dispatch

        stuck_pks = list(
            Booking.objects.filter(
                carrier_request_status='PENDING',
                updated_at__lt=cutoff,
            ).values_list('pk', flat=True)[:20]
        )

        count = 0
        for pk in stuck_pks:
            try:
                booking = Booking.objects.get(pk=pk)
                # Re-check status — may have been resolved by the original thread
                if booking.carrier_request_status != 'PENDING':
                    continue
                logger.info(
                    'Recovering stuck carrier dispatch for %s',
                    booking.booking_number,
                )
                carrier_dispatch.dispatch_carrier_booking(booking)
                count += 1
            except Booking.DoesNotExist:
                continue
            except Exception:
                logger.exception(
                    'Failed to recover carrier dispatch for booking pk=%s', pk,
                )

        return count

    def _process_webhook_retries(self):
        """Process pending webhook retries."""
        from integrations.webhook_dispatch import process_webhook_retries
        return process_webhook_retries()
