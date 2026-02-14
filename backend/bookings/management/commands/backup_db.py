import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create a timestamped backup of the SQLite database'

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
        backup_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f'db_{timestamp}.sqlite3'

        shutil.copy2(db_path, backup_path)
        self.stdout.write(self.style.SUCCESS(f'Backup created: {backup_path}'))
