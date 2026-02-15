"""
Create a timestamped SQLite backup with WAL checkpoint and integrity checks.

Features:
- WAL checkpoint before backup (flushes all pending writes)
- Uses Python sqlite3.backup() API for online-safe backup
- Verifies backup file size (warns if suspiciously small)
- Retention cleanup: --keep-days removes older backups
"""
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create a timestamped backup of the SQLite database with WAL checkpoint'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep-days', type=int, default=0,
            help='Delete backups older than N days (0 = keep all)',
        )

    def handle(self, *args, **options):
        engine = settings.DATABASES['default']['ENGINE']
        if 'sqlite' not in engine:
            self.stderr.write(self.style.ERROR(
                f'This command only supports SQLite. Current engine: {engine}. '
                'Use pg_dump for PostgreSQL.'
            ))
            return

        db_path = Path(settings.DATABASES['default']['NAME'])
        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f'Database not found: {db_path}'))
            return

        backup_dir = db_path.parent / 'backups'
        backup_dir.mkdir(mode=0o700, exist_ok=True)

        # 1. WAL checkpoint — flush pending writes to the main database file
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            self.stdout.write('WAL checkpoint completed.')
        except sqlite3.Error as e:
            self.stderr.write(self.style.WARNING(f'WAL checkpoint warning: {e}'))
        finally:
            if conn:
                conn.close()

        # 2. Backup using sqlite3.backup() API (online-safe)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'db_{timestamp}.sqlite3'

        source = None
        dest = None
        try:
            source = sqlite3.connect(str(db_path))
            dest = sqlite3.connect(str(backup_path))
            source.backup(dest)
        except sqlite3.Error as e:
            self.stderr.write(self.style.ERROR(f'Backup failed: {e}'))
            return
        finally:
            if dest:
                dest.close()
            if source:
                source.close()

        # 3. Verify backup size
        source_size = db_path.stat().st_size
        backup_size = backup_path.stat().st_size

        if backup_size < source_size * 0.5:
            self.stderr.write(self.style.WARNING(
                f'Backup size ({backup_size:,} bytes) is less than 50% of '
                f'source ({source_size:,} bytes) — verify integrity!'
            ))
        else:
            self.stdout.write(
                f'Backup: {backup_size:,} bytes '
                f'(source: {source_size:,} bytes)'
            )

        # Restrict file permissions (owner-only read/write on Linux/macOS)
        if os.name != 'nt':
            backup_path.chmod(0o600)

        self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_path}'))

        # 4. Retention cleanup
        keep_days = options['keep_days']
        if keep_days > 0:
            cutoff = datetime.now() - timedelta(days=keep_days)
            deleted = 0
            for old_backup in backup_dir.glob('db_*.sqlite3'):
                # Parse timestamp from filename: db_YYYYMMDD_HHMMSS.sqlite3
                try:
                    ts_str = old_backup.stem.replace('db_', '')
                    file_dt = datetime.strptime(ts_str, '%Y%m%d_%H%M%S')
                    if file_dt < cutoff:
                        old_backup.unlink()
                        deleted += 1
                except (ValueError, OSError):
                    continue

            if deleted:
                self.stdout.write(
                    f'Retention: deleted {deleted} backup(s) older than '
                    f'{keep_days} days.'
                )
