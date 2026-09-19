import logging
import time
from concurrent.futures import ThreadPoolExecutor

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from app.chatgpt.health_monitor import due_checks, run_check

logger = logging.getLogger("cron")


def check_with_connection(job):
    close_old_connections()
    try:
        delay = run_check(*job, reserve_confirmation=True)
        if delay:
            # Reserve this worker/lease so a full queue cannot postpone confirmation.
            close_old_connections()
            time.sleep(delay)
            run_check(*job)
    finally:
        close_old_connections()


class Command(BaseCommand):
    help = "Check upstream accounts and deliver confirmed health alerts"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = set()
            while True:
                close_old_connections()
                finished = {future for future in pending if future.done()}
                for future in finished:
                    try:
                        future.result()
                    except Exception:
                        logger.warning("账号健康检测任务失败，将在租约到期后重试")
                pending -= finished
                try:
                    jobs = due_checks(limit=4 - len(pending)) if len(pending) < 4 else []
                    for job in jobs:
                        pending.add(executor.submit(check_with_connection, job))
                except Exception:
                    logger.warning("账号健康检测调度暂不可用，将重试")
                if options["once"]:
                    for future in pending:
                        future.result()
                    return
                time.sleep(1)
