"""Hourly upstream quota snapshots, dispatched individually at 30–80 s intervals."""
import secrets
import time
from django.db import transaction
from app.chatgpt.models import AccountUsageSchedule, ChatgptAccount
from app.utils import req_gateway


def percent(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return round(min(100, max(0, value)), 1)


def normalize_usage(data):
    if not isinstance(data, dict):
        return {}
    windows, models = [], []
    def rate(name, value):
        if not isinstance(value, dict):
            return
        for window in ("primary_window", "secondary_window"):
            entry = value.get(window)
            if not isinstance(entry, dict):
                continue
            used = percent(entry.get("used_percent"))
            if used is not None:
                item = {"name": name, "window": window, "used_percent": used,
                    "reset_at": entry.get("reset_at") if type(entry.get("reset_at")) is int else None,
                    "window_seconds": entry.get("limit_window_seconds") if type(entry.get("limit_window_seconds")) is int else None}
                windows.append(item)
        if value.get("limit_reached") is True and not any(item["name"] == name and item["used_percent"] == 100 for item in windows):
            windows.append({"name": name, "window": "blocked", "used_percent": 100, "reset_at": None})
    rate("overall", data.get("rate_limit"))
    rate("code_review", data.get("code_review_rate_limit"))
    additional = data.get("additional_rate_limits") or []
    if isinstance(additional, dict):
        additional = [{"name": name, "rate_limit": value} for name, value in additional.items()]
    if isinstance(additional, list):
        for index, entry in enumerate(additional[:100]):
            if isinstance(entry, dict):
                name = str(entry.get("limit_name") or entry.get("name") or entry.get("metered_feature") or f"additional_{index}")[:100]
                rate(name, entry.get("rate_limit") or entry)
    usage = data.get("model_usage")
    if isinstance(usage, dict):
        for name, entry in list(usage.items())[:100]:
            if isinstance(entry, dict):
                models.append({"model": str(name)[:100], "available": entry.get("available") if type(entry.get("available")) is bool else None,
                    "available_at": entry.get("available_at") if type(entry.get("available_at")) is int else None})
                rate(str(name)[:100], entry)
    used = max((item["used_percent"] for item in windows if item["name"] != "code_review"), default=None)
    state = "unknown" if used is None else "full" if used >= 95 else "busy" if used >= 60 else "idle"
    return {"source": "upstream", "state": state, "used_percent": used,
        "remaining_percent": None if used is None else round(100-used, 1), "windows": windows, "models": models}


def public_usage(account, detailed=False):
    data = account.usage_snapshot or {}
    result = {key: data.get(key) for key in ("state", "used_percent", "remaining_percent")}
    result["state"] = result.get("state") or "unknown"
    result["checked_at"] = account.usage_checked_at
    result["next_check_at"] = account.usage_next_check_at or None
    result["stale"] = not account.usage_checked_at or int(time.time()) - account.usage_checked_at > 7200
    if detailed:
        result.update({"windows": data.get("windows", []), "models": data.get("models", []), "source": data.get("source"), "last_error": data.get("last_error", "")})
    return result


def run_next_check(now=None):
    now = int(time.time()) if now is None else now
    token = secrets.token_hex(16)
    with transaction.atomic():
        schedule, _ = AccountUsageSchedule.objects.get_or_create(pk=1)
        claimed = AccountUsageSchedule.objects.filter(pk=1, next_dispatch_at__lte=now, lease_until__lte=now).update(lease_until=now+180, lease_token=token)
        if not claimed:
            return False
        account = ChatgptAccount.objects.filter(auth_status=True, access_token_valid=True, usage_next_check_at__lte=now).order_by("usage_next_check_at", "id").first()
        if account is None:
            AccountUsageSchedule.objects.filter(pk=1, lease_token=token).update(lease_until=0, lease_token="", next_dispatch_at=now+5)
            return False
        version, identity, modified, account_token = account.web_identity_version, account.web_identity_id, account.updated_time, account.access_token
    try:
        data = req_gateway("post", "/api/account-usage", json={"access_token": account_token, "proxy_node_id": account.proxy_node_id}, timeout=(5, 75))
        snapshot = normalize_usage(data)
        if not snapshot or (snapshot["state"] == "unknown" and not snapshot.get("models") and not snapshot.get("windows")):
            raise ValueError("upstream quota unavailable")
        update = {"usage_snapshot": snapshot, "usage_checked_at": now, "usage_next_check_at": now+3600}
    except Exception:
        snapshot = dict(account.usage_snapshot or {})
        snapshot["last_error"] = "上游额度暂不可用，等待下次同步"
        update = {"usage_snapshot": snapshot, "usage_next_check_at": now+3600}
    finally:
        # A slow call still leaves a full random gap before the next request.
        finished = max(now, int(time.time()))
        AccountUsageSchedule.objects.filter(pk=1, lease_token=token).update(lease_until=0, lease_token="", next_dispatch_at=finished+30+secrets.randbelow(51))
    ChatgptAccount.objects.filter(pk=account.pk, web_identity_id=identity, web_identity_version=version, updated_time=modified).update(**update)
    return True
