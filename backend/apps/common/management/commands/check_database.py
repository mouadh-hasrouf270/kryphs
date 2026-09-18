from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
        if result != "ok":
            raise CommandError("Database integrity check failed.")
        self.stdout.write("ok")
