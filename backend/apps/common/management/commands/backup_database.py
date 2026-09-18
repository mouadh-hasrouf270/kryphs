import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Online SQLite backup plus local media; never includes environment secrets."

    def add_arguments(self, parser):
        parser.add_argument("--directory", default="backups")
        parser.add_argument("--retain", type=int, default=14)

    def handle(self, *args, **options):
        root = Path(options["directory"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        temp = root / f"cm-{stamp}.sqlite3"
        archive = root / f"cm-{stamp}.zip"
        with (
            closing(sqlite3.connect(settings.DATABASES["default"]["NAME"])) as source,
            closing(sqlite3.connect(temp)) as target,
        ):
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(temp, "database.sqlite3")
            if settings.MEDIA_ROOT.exists():
                for path in settings.MEDIA_ROOT.rglob("*"):
                    if path.is_file() and not path.is_symlink():
                        z.write(path, "media/" + path.relative_to(settings.MEDIA_ROOT).as_posix())
            z.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "created": stamp,
                        "encryption_key": "Back up APP_ENCRYPTION_KEY separately in a secure vault.",
                    }
                ),
            )
        temp.unlink()
        if options["retain"] > 0:
            for old in sorted(root.glob("cm-*.zip"), reverse=True)[options["retain"] :]:
                if old.resolve().parent == root:
                    old.unlink()
        self.stdout.write(str(archive))
