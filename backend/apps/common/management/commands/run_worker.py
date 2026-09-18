import signal
import time

from django.core.management.base import BaseCommand

from apps.common.jobs import run_once


class Command(BaseCommand):
    help = "Run one SQLite job worker. Use --once to drain one eligible job."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        stopped = False

        def stop(*_):
            nonlocal stopped
            stopped = True

        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        while not stopped:
            handled = run_once()
            if options["once"]:
                break
            if not handled:
                time.sleep(1)
