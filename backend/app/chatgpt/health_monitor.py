"""Persistent, bounded background probes; never changes account authorization."""
import time
import uuid
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from app.chatgpt.health_mail import MailDeliveryError, send_notification
from app.chatgpt.models import AccountHealthSettings, AccountHealthState, ChatgptAccount
from app.utils import req_gateway

CONFIRM_SECONDS = 18
LEASE_SECONDS = 600


def due_checks(limit=4):
    config = AccountHealthSettings.objects.only("revision").filter(pk=1, enabled=True).first()
    if not config:
        return []
    now = timezone.now()
    missing = ChatgptAccount.objects.filter(accounthealthstate__isnull=True).values_list("pk", flat=True)
    AccountHealthState.objects.bulk_create(
        [AccountHealthState(account_id=pk, next_check_at=now) for pk in missing], ignore_conflicts=True,
    )
    available = AccountHealthState.objects.filter(next_check_at__lte=now).filter(
        Q(lease_until__isnull=True) | Q(lease_until__lte=now)
    )
    # Confirmations take priority over fresh checks when many accounts are due.
    ids = list(available.order_by("-first_failure_at", "next_check_at").values_list("pk", flat=True)[:limit])
    claimed = []
    for pk in ids:
        token = uuid.uuid4().hex
        if available.filter(pk=pk).update(lease_token=token, lease_until=now + timedelta(seconds=LEASE_SECONDS)):
            claimed.append((pk, token, config.revision))
    return claimed


def probe(account):
    try:
        result = req_gateway("post", "/api/diagnose-chatgpt-auth", timeout=(5, 75), json={
            "access_token": account.access_token,
            "session_token": account.session_token,
            "proxy_node_id": account.proxy_node_id,
        })
        if not isinstance(result, dict) or not all(isinstance(result.get(key), bool) for key in ("access_token_valid", "session_token_valid")):
            return False, "账号诊断返回格式异常"
        healthy = result["access_token_valid"] or result["session_token_valid"]
        detail = "至少一种登录凭据可用" if healthy else "AccessToken 与 SessionToken 均不可用"
        # Do not overwrite credentials, plan, auth_status, or a concurrent edit.
        ChatgptAccount.objects.filter(pk=account.pk, updated_time=account.updated_time).update(
            access_token_valid=result["access_token_valid"], session_token_valid=result["session_token_valid"],
            last_check_at=int(time.time()), last_error="" if healthy else detail,
        )
        return healthy, detail
    except Exception:
        # Never include an upstream response, token or mail credential in alerts.
        return False, "账号健康检测请求失败（网关、网络或上游异常）"


def run_check(pk, token, revision, reserve_confirmation=False):
    owned = AccountHealthState.objects.filter(pk=pk, lease_token=token)
    keep_lease = False
    try:
        state = owned.select_related("account").first()
        config = AccountHealthSettings.objects.filter(pk=1, enabled=True, revision=revision).first()
        if not state or not config:
            return
        healthy, detail = probe(state.account)
        now = timezone.now()
        # A deleted/edited account or changed configuration invalidates the old result.
        if not owned.exists() or not AccountHealthSettings.objects.filter(pk=1, enabled=True, revision=revision).exists():
            return
        if not ChatgptAccount.objects.filter(pk=state.account_id, updated_time=state.account.updated_time).exists():
            owned.update(first_failure_at=None, notified=False, next_check_at=now)
            return
        updates = {"last_checked_at": now, "detail": detail,
                   "next_check_at": now + timedelta(minutes=config.interval_minutes)}
        if healthy:
            updates.update(first_failure_at=None, notified=False)
        elif not state.first_failure_at:
            updates.update(first_failure_at=now, next_check_at=now + timedelta(seconds=CONFIRM_SECONDS))
            keep_lease = reserve_confirmation
        elif now < state.first_failure_at + timedelta(seconds=CONFIRM_SECONDS):
            updates["next_check_at"] = state.first_failure_at + timedelta(seconds=CONFIRM_SECONDS)
        elif not state.notified:
            try:
                send_notification(config, f"账号状态异常 · {state.account.chatgpt_username}", (
                    f"账号：{state.account.chatgpt_username}\n"
                    f"账号 ID：{state.account_id}\n"
                    f"首次异常：{timezone.localtime(state.first_failure_at):%Y-%m-%d %H:%M:%S %Z}\n"
                    f"复检时间：{timezone.localtime(now):%Y-%m-%d %H:%M:%S %Z}\n"
                    f"检测结果：{detail}\n\n"
                    "该账号连续两次检测异常，请进入上游账号页面检查。通知不代表账号一定被封禁。"
                ), details=[
                    ("异常账号", state.account.chatgpt_username),
                    ("账号 ID", str(state.account_id)),
                    ("检测结果", detail),
                    ("首次异常", f"{timezone.localtime(state.first_failure_at):%Y-%m-%d %H:%M:%S %Z}"),
                    ("复检时间", f"{timezone.localtime(now):%Y-%m-%d %H:%M:%S %Z}"),
                ])
                updates["notified"] = True
                AccountHealthSettings.objects.filter(pk=1, revision=revision).update(last_sent_at=now, last_mail_error="")
            except MailDeliveryError as exc:
                updates["next_check_at"] = now + timedelta(minutes=2)
                AccountHealthSettings.objects.filter(pk=1, revision=revision).update(last_mail_error=str(exc))
        owned.update(**updates)
        return CONFIRM_SECONDS if keep_lease else None
    finally:
        if not keep_lease:
            owned.update(lease_token="", lease_until=None)
