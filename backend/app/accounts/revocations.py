"""Transactional, credential-free revocation outbox. Delivery is idempotent."""
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from rest_framework.authtoken.models import Token

from app.accounts.models import User, VisitorSession, GatewayRevocation, LoginSession
from app.accounts.session_authority import authorization_version
from app.utils import req_gateway

POLICY_FIELDS = ("username", "password", "is_active", "expired_date", "gptcar_list", "model_limit",
                 "isolated_session", "allow_multiple_sessions", "mcp_isolation", "skills_isolation", "mcp_allowlist",
                 "skills_allowlist", "capability_policy_initialized", "force_chat_mode",
                 "model_isolation", "model_policies",
                 "hide_chat_work_toggle", "hide_library", "hide_suggestions",
                 "daily_quota", "monthly_quota",
                 "is_staff", "is_superuser")


def enqueue(user, token, *, subject=None, expires_at=None):
    event, _ = GatewayRevocation.objects.get_or_create(
        subject=subject or user.username, version=authorization_version(user, token.key),
        defaults={"include_visitors": subject is None and user.username == settings.FREE_ACCOUNT_USERNAME,
                  "expires_at": expires_at or token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS)},
    )
    transaction.on_commit(lambda: deliver(event.pk))
    return event.pk


def deliver(event_id):
    now = timezone.now()
    # An atomic delivery lease permits multiple worker processes without a retry storm.
    if not GatewayRevocation.objects.filter(pk=event_id, next_attempt_at__lte=now).update(
        next_attempt_at=now + timedelta(seconds=30),
    ):
        return
    event = GatewayRevocation.objects.get(pk=event_id)
    if event.expires_at <= now:
        event.delete()
        return
    try:
        response = req_gateway("post", "/api/revoke-authorization", timeout=(1, 2), json={
            "subject": event.subject, "version": event.version,
            "include_visitors": event.include_visitors, "expires_at": int(event.expires_at.timestamp()),
        })
        if not isinstance(response, dict) or response.get("revoked") is not True:
            raise ValueError("Gateway did not acknowledge revocation")
    except Exception:
        GatewayRevocation.objects.filter(pk=event_id).update(
            attempts=event.attempts + 1,
            next_attempt_at=timezone.now() + timedelta(seconds=min(60, 2 ** min(event.attempts + 1, 6))),
        )
    else:
        event.delete()


@receiver(pre_delete, sender=Token)
@receiver(pre_delete, sender=LoginSession)
def token_deleted(sender, instance, **kwargs):
    enqueue(instance.user, instance)


@receiver(pre_delete, sender=VisitorSession)
def visitor_deleted(sender, instance, **kwargs):
    token = Token.objects.filter(user_id=instance.user_id).first()
    if token:
        enqueue(instance.user, token, subject=f"{instance.user.username}:{instance.sid}", expires_at=instance.expires_at)


@receiver(pre_save, sender=User)
def policy_changing(sender, instance, update_fields=None, raw=False, **kwargs):
    if raw or not instance.pk:
        return
    old = User.objects.select_for_update().filter(pk=instance.pk).first()
    if old and old.username != instance.username:
        from app.accounts.models import RetiredUsername
        RetiredUsername.objects.get_or_create(name=old.username.strip().casefold())
    if old:
        instance.authorization_version = old.authorization_version
    if old and any(getattr(old, field) != getattr(instance, field)
                   for field in POLICY_FIELDS if update_fields is None or field in update_fields):
        tokens = list(Token.objects.filter(user_id=old.pk)) + list(LoginSession.objects.filter(user_id=old.pk))
        for token in tokens:
            enqueue(old, token)
        if old.can_use_multiple_sessions and not instance.can_use_multiple_sessions:
            LoginSession.objects.filter(user_id=old.pk).delete()
        # update_fields may exclude this internal field: update it inside the same transaction.
        instance.authorization_version = uuid.uuid4()
        User.objects.filter(pk=old.pk).update(authorization_version=instance.authorization_version)


@receiver(pre_delete,sender=User)
def retire_deleted_username(sender,instance,**kwargs):
    from app.accounts.models import RetiredUsername
    RetiredUsername.objects.get_or_create(name=instance.username.strip().casefold())
