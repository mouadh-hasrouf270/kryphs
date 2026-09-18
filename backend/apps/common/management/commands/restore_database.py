import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Verify and restore a backup into a NEW directory. Stop all services before switching paths."

    def add_arguments(self, parser):
        parser.add_argument("archive")
        parser.add_argument("--destination", required=True)

    def handle(self, *args, **options):
        destination = Path(options["destination"]).resolve()
        if destination.exists():
            raise CommandError("Destination must not exist; existing data is never overwritten.")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with zipfile.ZipFile(options["archive"]) as archive:
                for member in archive.infolist():
                    target = (root / member.filename).resolve()
                    if not target.is_relative_to(root):
                        raise CommandError("Unsafe archive path.")
                    if member.file_size > 20 * 1024**3:
                        raise CommandError("Oversized backup member.")
                archive.extractall(root)
            db = root / "database.sqlite3"
            if not db.exists():
                raise CommandError("Backup database is missing.")
            with closing(sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise CommandError("Integrity check failed.")
            shutil.copytree(root, destination)
        self.stdout.write(
            f"Verified restore: {destination}. Stop web/worker; set DATABASE_PATH and MEDIA_ROOT to this directory before restarting. Restore the original APP_ENCRYPTION_KEY separately."
        )
