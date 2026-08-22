import json
import time

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import Announcement, User, VisitLog
from app.chatgpt.models import ChatgptAccount, ChatgptCar
from app.fields import decrypt_value, encrypt_value
from app.utils import req_gateway


BACKUP_VERSION = 2
GATEWAY_BACKUP_VERSION = 2
DJANGO_BACKUP_COLLECTIONS = (
    "groups",
    "users",
    "announcements",
    "chatgpt_accounts",
    "chatgpt_cars",
    "visit_logs",
    "tokens",
    "sessions",
    "admin_logs",
)
GATEWAY_BACKUP_COLLECTIONS = (
    "chatgpt_accounts",
    "gateway_sessions",
    "settings",
    "conversation_owners",
    "visit_logs",
    "conversation_statistics",
    "conversation_model_statistics",
)


def _iso(value):
    return value.isoformat() if value else None


def _permission_key(permission):
    return f"{permission.content_type.app_label}.{permission.codename}"


def _export_django_data():
    groups = Group.objects.prefetch_related("permissions__content_type").order_by("id")
    users = User.objects.prefetch_related("groups", "user_permissions__content_type").order_by("id")
    return {
        "groups": [
            {
                "id": group.id,
                "name": group.name,
                "permissions": [_permission_key(item) for item in group.permissions.all()],
            }
            for group in groups
        ],
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "password": user.password,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "last_login": _iso(user.last_login),
                "date_joined": _iso(user.date_joined),
                "remark": user.remark,
                "isolated_session": user.isolated_session,
                "gptcar_list": user.gptcar_list,
                "model_limit": user.model_limit,
                "expired_date": _iso(user.expired_date),
                "daily_quota": user.daily_quota,
                "monthly_quota": user.monthly_quota,
                "force_chat_mode": user.force_chat_mode,
                "allow_admin_view_conversation_titles": user.allow_admin_view_conversation_titles,
                "groups": list(user.groups.values_list("name", flat=True)),
                "user_permissions": [
                    _permission_key(item) for item in user.user_permissions.all()
                ],
            }
            for user in users
        ],
        "announcements": [
            {
                "id": item.id,
                "title": item.title,
                "content": item.content,
                "scope": item.scope,
                "target_username": item.target_user.username if item.target_user else None,
                "is_active": item.is_active,
                "start_at": _iso(item.start_at),
                "end_at": _iso(item.end_at),
                "display_timezone": item.display_timezone,
                "created_by_username": item.created_by.username if item.created_by else None,
                "created_at": _iso(item.created_at),
                "updated_at": _iso(item.updated_at),
            }
            for item in Announcement.objects.select_related("target_user", "created_by").order_by("id")
        ],
        "chatgpt_accounts": [
            {
                "id": account.id,
                **{
                    field: getattr(account, field)
                    for field in (
                        "chatgpt_username",
                        "auth_status",
                        "plan_type",
                        "access_token",
                        "session_token",
                        "extra_cookies",
                        "refresh_token",
                        "refresh_client_id",
                        "access_token_valid",
                        "session_token_valid",
                        "proxy_node_id",
                        "last_check_at",
                        "last_error",
                        "login_count",
                        "remark",
                        "created_time",
                        "updated_time",
                    )
                },
            }
            for account in ChatgptAccount.objects.order_by("id")
        ],
        "chatgpt_cars": list(
            ChatgptCar.objects.order_by("id").values(
                "id", "car_name", "remark", "gpt_account_list", "created_time", "updated_time"
            )
        ),
        "visit_logs": list(
            VisitLog.objects.order_by("id").values(
                "id", "username", "chatgpt_username", "log_type", "created_at", "ip", "user_agent"
            )
        ),
        "tokens": [
            {
                "key": token.key,
                "username": token.user.username,
                "created": _iso(token.created),
            }
            for token in Token.objects.select_related("user").order_by("key")
        ],
        "sessions": [
            {
                "session_key": item.session_key,
                "session_data": item.session_data,
                "expire_date": _iso(item.expire_date),
            }
            for item in Session.objects.order_by("session_key")
        ],
        "admin_logs": [
            {
                "id": item.id,
                "action_time": _iso(item.action_time),
                "username": item.user.username,
                "content_type": (
                    f"{item.content_type.app_label}.{item.content_type.model}"
                    if item.content_type
                    else None
                ),
                "object_id": item.object_id,
                "object_repr": item.object_repr,
                "action_flag": item.action_flag,
                "change_message": item.change_message,
            }
            for item in LogEntry.objects.select_related("user", "content_type").order_by("id")
        ],
    }


def _require_complete_django_backup(payload):
    if not isinstance(payload, dict):
        raise ValidationError({"archive": "备份缺少 Django 数据"})
    for name in DJANGO_BACKUP_COLLECTIONS:
        if not isinstance(payload.get(name), list):
            raise ValidationError({"archive": f"完整备份缺少 {name}"})


def _require_complete_gateway_backup(payload):
    if not isinstance(payload, dict):
        raise ValidationError({"archive": "完整备份缺少 Gateway 数据"})
    if payload.get("version") != GATEWAY_BACKUP_VERSION:
        raise ValidationError({"archive": "Gateway 备份版本不匹配"})
    for name in GATEWAY_BACKUP_COLLECTIONS:
        if not isinstance(payload.get(name), list):
            raise ValidationError({"archive": f"完整 Gateway 备份缺少 {name}"})


def _restore_django_and_gateway(gateway_payload, restore_django):
    previous_gateway = req_gateway("get", "/api/backup/export")
    try:
        req_gateway("post", "/api/backup/restore", json=gateway_payload)
        restore_django()
    except Exception as restore_error:
        try:
            req_gateway("post", "/api/backup/restore", json=previous_gateway)
        except Exception as rollback_error:
            raise ValidationError(
                {"archive": f"恢复失败，且 Gateway 回滚失败：{rollback_error}"}
            ) from restore_error
        raise


def _parse_datetime(value, fallback=None):
    if not value:
        return fallback
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise ValidationError({"archive": f"无效时间：{value}"})
    return parsed


def _parse_date_value(value):
    if not value:
        return None
    parsed = parse_date(str(value))
    if parsed is None:
        raise ValidationError({"archive": f"无效日期：{value}"})
    return parsed


def _resolve_named_items(keys, values, label):
    missing = [key for key in keys if key not in values]
    if missing:
        raise ValidationError({"archive": f"备份引用了不存在的{label}：{missing[0]}"})
    return [values[key] for key in keys]


def _permission_map():
    return {
        _permission_key(permission): permission
        for permission in Permission.objects.select_related("content_type")
    }


def _restore_complete_django(payload):
    _require_complete_django_backup(payload)
    permissions = _permission_map()
    content_types = {
        f"{item.app_label}.{item.model}": item for item in ContentType.objects.all()
    }

    with transaction.atomic():
        LogEntry.objects.all().delete()
        Announcement.objects.all().delete()
        Token.objects.all().delete()
        Session.objects.all().delete()
        VisitLog.objects.all().delete()
        User.objects.all().delete()
        Group.objects.all().delete()
        ChatgptCar.objects.all().delete()
        ChatgptAccount.objects.all().delete()

        groups = {}
        for raw in payload["groups"]:
            data = dict(raw)
            permission_keys = data.pop("permissions", [])
            group = Group.objects.create(**data)
            group.permissions.set(_resolve_named_items(permission_keys, permissions, "权限"))
            groups[group.name] = group

        for raw in payload["chatgpt_accounts"]:
            ChatgptAccount.objects.create(**dict(raw))
        for raw in payload["chatgpt_cars"]:
            ChatgptCar.objects.create(**dict(raw))

        users = {}
        for raw in payload["users"]:
            data = dict(raw)
            group_names = data.pop("groups", [])
            permission_keys = data.pop("user_permissions", [])
            data["last_login"] = _parse_datetime(data.get("last_login"))
            data["date_joined"] = _parse_datetime(
                data.get("date_joined"), fallback=timezone.now()
            )
            data["expired_date"] = _parse_date_value(data.get("expired_date"))
            user = User.objects.create(**data)
            user.groups.set(_resolve_named_items(group_names, groups, "用户组"))
            user.user_permissions.set(_resolve_named_items(permission_keys, permissions, "权限"))
            users[user.username] = user

        for raw in payload["announcements"]:
            data = dict(raw)
            target_username = data.pop("target_username", None)
            created_by_username = data.pop("created_by_username", None)
            if target_username and target_username not in users:
                raise ValidationError({"archive": f"公告目标用户不存在：{target_username}"})
            if created_by_username and created_by_username not in users:
                raise ValidationError({"archive": f"公告创建者不存在：{created_by_username}"})
            data["target_user"] = users.get(target_username)
            data["created_by"] = users.get(created_by_username)
            for field in ("start_at", "end_at"):
                data[field] = _parse_datetime(data.get(field))
            created_at = _parse_datetime(data.pop("created_at", None), fallback=timezone.now())
            updated_at = _parse_datetime(data.pop("updated_at", None), fallback=created_at)
            announcement = Announcement.objects.create(**data)
            Announcement.objects.filter(pk=announcement.pk).update(
                created_at=created_at, updated_at=updated_at
            )

        for raw in payload["visit_logs"]:
            VisitLog.objects.create(**dict(raw))
        for raw in payload["tokens"]:
            data = dict(raw)
            username = data.pop("username")
            if username not in users:
                raise ValidationError({"archive": f"令牌用户不存在：{username}"})
            data["user"] = users[username]
            created = _parse_datetime(data.pop("created", None), fallback=timezone.now())
            token = Token.objects.create(**data)
            Token.objects.filter(pk=token.pk).update(created=created)
        for raw in payload["sessions"]:
            data = dict(raw)
            data["expire_date"] = _parse_datetime(data.get("expire_date"))
            Session.objects.create(**data)
        for raw in payload["admin_logs"]:
            data = dict(raw)
            username = data.pop("username")
            content_type = data.pop("content_type", None)
            if username not in users:
                raise ValidationError({"archive": f"管理日志用户不存在：{username}"})
            if content_type and content_type not in content_types:
                raise ValidationError({"archive": f"管理日志内容类型不存在：{content_type}"})
            data["user"] = users[username]
            data["content_type"] = content_types.get(content_type)
            data["action_time"] = _parse_datetime(
                data.get("action_time"), fallback=timezone.now()
            )
            LogEntry.objects.create(**data)


def _restore_legacy_backup(payload):
    with transaction.atomic():
        for raw in payload.get("chatgpt_accounts", []):
            data = dict(raw)
            account_id = data.pop("id")
            username = data.pop("chatgpt_username")
            ChatgptAccount.objects.update_or_create(
                id=account_id, defaults={"chatgpt_username": username, **data}
            )
        for raw in payload.get("chatgpt_cars", []):
            data = dict(raw)
            car_id = data.pop("id")
            name = data.pop("car_name")
            ChatgptCar.objects.update_or_create(
                id=car_id, defaults={"car_name": name, **data}
            )
        for raw in payload.get("users", []):
            data = dict(raw)
            username = data.pop("username")
            User.objects.update_or_create(username=username, defaults=data)
        for raw in payload.get("visit_logs", []):
            data = dict(raw)
            log_id = data.pop("id")
            VisitLog.objects.update_or_create(id=log_id, defaults=data)


class UnifiedBackupView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        payload = {
            "version": BACKUP_VERSION,
            "created_at": int(time.time()),
            "django": _export_django_data(),
            "gateway": req_gateway("get", "/api/backup/export"),
        }
        archive = encrypt_value(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        response = Response({"archive": archive})
        response["Content-Disposition"] = (
            f'attachment; filename="chatgpt-mirror-backup-{payload["created_at"]}.json"'
        )
        return response

    def post(self, request):
        if request.data.get("confirm") != "RESTORE":
            raise ValidationError({"confirm": "恢复操作必须明确提交 RESTORE"})
        archive = str(request.data.get("archive") or "")
        try:
            payload = json.loads(decrypt_value(archive))
        except Exception:
            raise ValidationError({"archive": "备份文件无效或加密密钥不匹配"})

        version = payload.get("version")
        if version == 1:
            _restore_django_and_gateway(
                payload.get("gateway") or {}, lambda: _restore_legacy_backup(payload)
            )
            return Response({"message": "旧版统一备份已恢复；旧备份不包含新增的全部数据"})
        if version != BACKUP_VERSION:
            raise ValidationError({"archive": "不支持的备份版本"})

        django_payload = payload.get("django")
        gateway_payload = payload.get("gateway")
        _require_complete_django_backup(django_payload)
        _require_complete_gateway_backup(gateway_payload)
        _restore_django_and_gateway(
            gateway_payload, lambda: _restore_complete_django(django_payload)
        )

        return Response({"message": "全部应用数据已恢复；如备份会话已过期，请重新登录"})
