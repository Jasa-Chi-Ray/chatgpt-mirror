import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone
from app.accounts.models import GatewayRevocation
from app.accounts.revocations import deliver


class Command(BaseCommand):
    help = "Deliver pending gateway revocations with persistent retry"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            ids = list(GatewayRevocation.objects.filter(next_attempt_at__lte=timezone.now())
                       .order_by("next_attempt_at").values_list("pk", flat=True)[:100])
            for event_id in ids:
                deliver(event_id)
            if options["once"]:
                return
            time.sleep(2)
