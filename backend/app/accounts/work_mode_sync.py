"""Durable post-commit synchronization; failures never preserve old local logins."""
import uuid
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from app.accounts.models import User, UserWorkModeSync
from app.utils import req_gateway


def enqueue(user):
    event,_=UserWorkModeSync.objects.update_or_create(user=user,defaults={
        'revision':uuid.uuid4(),'next_attempt_at':timezone.now(),'attempts':0})
    transaction.on_commit(lambda:deliver(event.pk))


def deliver(pk):
    now=timezone.now()
    if not UserWorkModeSync.objects.filter(pk=pk,next_attempt_at__lte=now).update(next_attempt_at=now+timedelta(seconds=30)):return
    event=UserWorkModeSync.objects.select_related('user').filter(pk=pk).first()
    if not event:return
    mode=event.user.force_chat_mode
    try:
        req_gateway('post','/api/user-work-mode',timeout=(1,2),json={'user_name':event.user.username,'force_chat_mode':mode})
    except Exception:
        UserWorkModeSync.objects.filter(pk=pk,revision=event.revision).update(attempts=event.attempts+1,next_attempt_at=now+timedelta(seconds=min(60,2**min(event.attempts+1,6))))
    else:
        UserWorkModeSync.objects.filter(pk=pk,revision=event.revision).delete()
        # An old in-flight notification must not become the final persisted mode.
        current=User.objects.filter(pk=event.user_id).first()
        if current and current.force_chat_mode!=mode:
            with transaction.atomic():enqueue(current)
