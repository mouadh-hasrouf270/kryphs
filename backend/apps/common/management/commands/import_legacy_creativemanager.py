import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.common.legacy import inspect_and_import


class Command(BaseCommand):
    help = "Validate/import supported legacy entities from a read-only SQLite source."

    def add_arguments(self, parser):
        parser.add_argument("--database", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--allow-partial", action="store_true")
        parser.add_argument("--report", default="migration-report.json")

    def handle(self, *args, **options):
        report = inspect_and_import(
            options["database"], options["dry_run"], options["allow_partial"]
        )
        Path(options["report"]).write_text(json.dumps(report, indent=2), encoding="utf-8")
        self.stdout.write(
            json.dumps({k: report[k] for k in ["counts", "imported", "committed"]}, indent=2)
        )
        if not options["dry_run"] and not report["committed"]:
            raise CommandError(
                "Import rolled back. Resolve report findings or explicitly use --allow-partial after reviewing unsupported entities."
            )
