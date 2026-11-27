import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from app.chatgpt.usage_monitor import run_next_check


class Command(BaseCommand):
    help = "Refresh upstream quota snapshots with staggered hourly scheduling"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            try:
                run_next_check()
            except Exception:
                pass  # Never log upstream credential-bearing exceptions.
            finally:
                close_old_connections()
            if options["once"]:
                return
            time.sleep(1)
