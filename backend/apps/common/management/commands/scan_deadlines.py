from django.core.management.base import BaseCommand

from apps.notifications.services import scan_deadlines


class Command(BaseCommand):
    help = "Generate deduplicated due-soon and overdue notifications. Schedule daily or hourly."

    def handle(self, *args, **options):
        self.stdout.write(str(scan_deadlines()))
