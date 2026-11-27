"""Local identity and CSRF checks stay in Django; upstream authentication stays in Rust."""
import secrets
import re

from django.conf import settings
from django.db import transaction
from django.core import signing
from django.utils.crypto import constant_time_compare
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.session_authority import gateway_authorization, capability_aliases, account_model_policy
from app.accounts.session_authority import digest
from app.accounts.views.announcements import active_login_block_for
from app.chatgpt.models import ChatgptAccount
from app.utils import get_request_subject, req_gateway

BIND_COOKIE = "mirror_web_login_binding"
FLOW_COOKIE = "mirror_web_login"


class WebLoginSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("start", "complete", "status", "activate", "disconnect", "cancel"))
    pool = serializers.BooleanField(default=False)
    id = serializers.RegexField(r"^[a-f0-9]{64}$", required=False, allow_blank=True, default="")
    proxy_node_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    flow = serializers.RegexField(r"^[a-f0-9]{64}$", required=False, allow_blank=True, default="")
    embedded = serializers.BooleanField(default=False)
    account_id = serializers.IntegerField(required=False, min_value=1)
    overwrite_token = serializers.CharField(required=False, allow_blank=True, max_length=1024, default="")
    delete_upstream = serializers.BooleanField(default=False)


def login_policy(request):
    user = request.user
    return {
        "user_name": get_request_subject(request), "authorization": gateway_authorization(request),
        "isolated_session": True,
        "mcp_isolation": user.mcp_isolation and user.capability_policy_initialized,
        "skills_isolation": user.skills_isolation and user.capability_policy_initialized,
        "mcp_allowed_ids": capability_aliases(user, "mcp_allowlist"),
        "skills_allowed_ids": capability_aliases(user, "skills_allowlist"),
        "limits": [item for item in (user.model_limit or []) if isinstance(item, str)],
        # Like account_model_policy(), an account without a configured model
        # policy uses the upstream model list. An empty allowlist with isolation
        # enabled would otherwise prevent every newly connected account chatting.
        "model_isolation": False,
        "model_allowed_ids": [],
        "model_rate_limits": {},
        "daily_quota": user.daily_quota, "monthly_quota": user.monthly_quota,
        "force_chat_mode": user.force_chat_mode, "hide_chat_work_toggle": user.hide_chat_work_toggle,
        "hide_library": user.hide_library, "hide_suggestions": user.hide_suggestions,
        "_browser_session_hash": digest(request.COOKIES.get("mirror_api_session") or str(request.auth)),
    }


@transaction.atomic
def apply_web_credentials(account, data, *, touch_modified=False):
    """Update the known account only; never select an account using a callback's email."""
    info = data.get("user_info") or {}
    identity_id = data.get("web_identity_id") or ""
    if not re.fullmatch(r"[a-f0-9]{64}", identity_id):
        raise ValidationError("官网连接标识无效")
    current = account if account._state.adding else ChatgptAccount.objects.select_for_update().get(pk=account.pk)
    if account.web_identity_id and current.web_identity_id != account.web_identity_id:
        raise ValidationError("官网连接已变更，请重新载入")
    if current.web_identity_id and current.web_identity_id != identity_id:
        raise ValidationError("官网连接已变更，请重新载入")
    if current.chatgpt_username.casefold() != str(info.get("email") or "").casefold():
        raise ValidationError("官网连接与原账号不一致")
    version = data.get("credential_version")
    if type(version) is not int or not 1 <= version <= 2**63 - 1:
        raise ValidationError("官网连接凭据版本无效")
    if current.web_identity_id == identity_id and current.web_identity_version > version:
        account.refresh_from_db()
        return
    if not data.get("access_token") or (not current.web_identity_id and not data.get("session_token")):
        raise ValidationError("官网连接未返回完整凭据")
    account.web_identity_id = identity_id
    account.web_identity_version = version
    account.access_token = data["access_token"]
    account.session_token = data.get("session_token")
    account.extra_cookies = data.get("extra_cookies") or []
    account.refresh_token = account.refresh_client_id = None
    account.plan_type = info.get("plan_type") or current.plan_type
    account.access_token_valid = bool(data.get("access_token_valid"))
    account.session_token_valid = bool(data.get("session_token_valid"))
    account.auth_status = True
    account.last_error = data.get("last_error") or ""
    import time
    account.last_check_at = data.get("last_check_at") or int(time.time())
    fields = ["web_identity_id", "web_identity_version", "access_token", "session_token", "extra_cookies",
              "refresh_token", "refresh_client_id", "plan_type", "access_token_valid", "session_token_valid",
              "auth_status", "last_error", "last_check_at"]
    if current.web_identity_id != identity_id or current.web_identity_version < version:
        account.usage_next_check_at = 0
        fields.append("usage_next_check_at")
    if touch_modified or account._state.adding:
        account.updated_time = account.last_check_at
        fields.append("updated_time")
    account.save(update_fields=fields if not account._state.adding else None)


def refresh_pool_credentials(request, account):
    if not account.web_identity_id:
        return
    result = req_gateway("post", "/api/web-login", json={
        "action": "pool-credentials", "owner": get_request_subject(request),
        "authorization": gateway_authorization(request), "id": account.web_identity_id,
    })
    apply_web_credentials(account, result)


class WebLoginView(APIView):
    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def ensure_user(self, request, pool=False):
        if request.user.username == settings.FREE_ACCOUNT_USERNAME:
            raise PermissionDenied("请先登录个人账号后连接")
        if pool and not request.user.is_staff:
            raise PermissionDenied("仅管理员可录入账号池")
        if active_login_block_for(request.user):
            raise PermissionDenied("公告生效期间，暂不能连接 ChatGPT")

    def get(self, request):
        pool = request.query_params.get("pool", "false") == "true"
        self.ensure_user(request, pool)
        result = req_gateway("post", "/api/web-login", json={
            "action": "list", "owner": get_request_subject(request),
            "authorization": gateway_authorization(request), "pool": pool,
        })
        connections = result.get("connections") or []
        if pool:
            personal = req_gateway("post", "/api/web-login", json={"action": "list", "owner": get_request_subject(request), "authorization": gateway_authorization(request), "pool": False})
            connections += personal.get("connections") or []
        response = Response({"connections": connections})
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response

    def post(self, request):
        serializer = WebLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.ensure_user(request, data["pool"])
        if data.get("proxy_node_id") and not request.user.is_staff:
            raise PermissionDenied("仅管理员可选择登录代理节点")
        binding = request.COOKIES.get(BIND_COOKIE, "")
        if not re.fullmatch(r"[a-f0-9]{64}", binding):
            binding = secrets.token_hex(32)
        policy = login_policy(request)
        if data["action"] == "start":
            policy["_embedded"] = data["embedded"]
            if data.get("account_id"):
                if not data["pool"] or not request.user.is_staff:
                    raise PermissionDenied("仅管理员可更新上游账号")
                target = ChatgptAccount.objects.filter(pk=data["account_id"]).first()
                if target is None:
                    raise ValidationError("原上游账号已不存在")
                if data["id"] and data["id"] != (target.web_identity_id or ""):
                    raise ValidationError("官网连接与待更新账号不一致")
                data["id"] = target.web_identity_id or ""
                data["pool"] = target.automation_owner_id is None
                data["proxy_node_id"] = target.proxy_node_id
                policy.update({"_expected_email": target.chatgpt_username,
                               "_pool_target_account_id": target.pk, "_force_renewal": True})
        if data["action"] == "activate" and not data["pool"] and request.user.model_isolation and request.user.model_policies:
            owned = req_gateway("post", "/api/web-login", json={
                "action": "list", "owner": get_request_subject(request),
                "authorization": gateway_authorization(request), "pool": False,
            })
            connection = next((item for item in owned.get("connections", []) if item.get("id") == data["id"]), None)
            if connection is None:
                raise ValidationError("账号连接不存在")
            account = ChatgptAccount.objects.filter(chatgpt_username__iexact=connection.get("email") or "").first()
            if account is not None:
                policy.update(account_model_policy(request.user, account))
        payload = {
            **data, "owner": get_request_subject(request), "authorization": gateway_authorization(request),
            "binding": binding, "flow_token": data.get("flow") or request.COOKIES.get(FLOW_COOKIE, ""),
            "policy": policy,
        }
        if data["action"] == "complete":
            preview = req_gateway("post", "/api/web-login", json={**payload, "action": "preview"})
            if preview.get("status") != "ready":
                return Response({"status": "pending"})
            with transaction.atomic():
                email = str(preview.get("email") or "")
                target_id = preview.get("target_account_id")
                accounts = ChatgptAccount.objects.select_for_update()
                account = accounts.filter(pk=target_id).first() if target_id else accounts.filter(chatgpt_username__iexact=email).first()
                if target_id and account is None:
                    raise ValidationError("原上游账号已不存在，请重新发起自动化链接")
                if account and not request.user.is_staff and account.automation_owner_id != request.user.pk:
                    raise PermissionDenied("该官网账号已由其他用户或管理员维护，请联系管理员处理")
                conflict = account is not None and not target_id and (not preview.get("reconnect_id") or preview.get("reconnect_id") != account.web_identity_id)
                if conflict:
                    confirmation = {"owner": request.user.pk, "flow": payload["flow_token"], "account": account.pk,
                                    "updated": account.updated_time, "version": account.web_identity_version, "identity": account.web_identity_id}
                    try:
                        accepted = signing.loads(data["overwrite_token"], salt="automation-overwrite", max_age=600)
                    except signing.BadSignature:
                        accepted = None
                    if accepted != confirmation:
                        return Response({"status": "overwrite_required", "email": email,
                            "overwrite_token": signing.dumps(confirmation, salt="automation-overwrite"),
                            "message": "检测到相同上游账号，是否覆盖其登录凭据并改为当前自动化链接？"})
                result = req_gateway("post", "/api/web-login", json=payload)
                if result.get("status") == "connected":
                    credentials = result.get("credentials") or {}
                    if account is None:
                        import time
                        account = ChatgptAccount(chatgpt_username=email, created_time=int(time.time()),
                            automation_owner=None if data["pool"] else request.user)
                    elif account.web_identity_id and account.web_identity_id != credentials.get("web_identity_id"):
                        from app.chatgpt.account_lifecycle import disconnect_identity
                        disconnect_identity(request, account.web_identity_id, account.automation_owner_id is None)
                        account.web_identity_id = None
                        account.web_identity_version = 0
                        account.save(update_fields=["web_identity_id", "web_identity_version"])
                    account.proxy_node_id = credentials.get("proxy_node_id")
                    if not target_id:
                        account.automation_owner = None if data["pool"] else request.user
                    apply_web_credentials(account, credentials, touch_modified=True)
                    account.save(update_fields=["proxy_node_id", "automation_owner"])
        elif data["action"] == "disconnect":
            from app.chatgpt.account_lifecycle import clear_automation_credentials, delete_upstream_account
            account = ChatgptAccount.objects.filter(web_identity_id=data["id"]).first()
            if account and not request.user.is_staff and account.automation_owner_id != request.user.pk:
                raise PermissionDenied("不能解除其他用户的自动化链接")
            if account and data["delete_upstream"]:
                delete_upstream_account(request, account)
                result = {"message": "自动化链接及上游账号已删除"}
            else:
                result = req_gateway("post", "/api/web-login", json=payload)
                if account:
                    clear_automation_credentials(account)
        else:
            result = req_gateway("post", "/api/web-login", json=payload)
        # Return an explicit allowlist, never an upstream credential response.
        response = Response({key: result[key] for key in ("authorize_url", "expires_in", "status", "connection", "login_url", "message") if key in result})
        if data["action"] == "start":
            response.data["pool"] = data["pool"]
        response["Cache-Control"] = "private, no-store"
        response["Referrer-Policy"] = "no-referrer"
        if data["action"] == "start":
            response.set_cookie(BIND_COOKIE, binding, max_age=1200, httponly=True,
                                secure=settings.SESSION_COOKIE_SECURE, samesite="Lax", path="/")
        if data["action"] == "complete" and result.get("status") == "connected" and request.COOKIES.get(FLOW_COOKIE) == payload["flow_token"]:
            response.delete_cookie(FLOW_COOKIE, path="/", samesite="Lax")
        if data["action"] == "complete" and result.get("status") == "connected" and re.fullmatch(r"[a-f0-9]{64}", payload["flow_token"]):
            response.delete_cookie("oai-did", path="/__upstream-login/" + payload["flow_token"], samesite="Lax")
        return response


class WebLoginSyncView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        supplied = request.META.get("HTTP_AUTHORIZATION", "")
        expected = "Bearer " + settings.GATEWAY_ADMIN_SECRET
        if not constant_time_compare(supplied, expected):
            return Response({"message": "服务认证失败"}, status=401)
        data = request.data
        identity_id = str(data.get("web_identity_id") or "")
        if not re.fullmatch(r"[a-f0-9]{64}", identity_id):
            raise ValidationError("官网连接标识无效")
        with transaction.atomic():
            account = ChatgptAccount.objects.select_for_update().filter(web_identity_id=identity_id).first()
            if account:
                apply_web_credentials(account, data)
        return Response({"updated": bool(account)})


class WebLoginOwnersView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def post(self, request):
        if not constant_time_compare(request.META.get("HTTP_AUTHORIZATION", ""), "Bearer " + settings.GATEWAY_ADMIN_SECRET):
            return Response({"message": "服务认证失败"}, status=401)
        owners = request.data.get("owners")
        if not isinstance(owners, list) or len(owners) > 400:
            raise ValidationError("用户清理批次无效")
        parsed = {}
        for owner in owners:
            if not isinstance(owner, str) or len(owner) > 256:
                raise ValidationError("用户清理标识无效")
            uid, separator, username = owner.partition(":")
            if not separator or not uid.isdigit() or len(uid) > 18:
                raise ValidationError("用户清理标识无效")
            parsed[owner] = (int(uid), username)
        from app.accounts.models import User
        users = dict(User.objects.filter(pk__in=[uid for uid, _ in parsed.values()]).values_list("pk", "username"))
        return Response({"present": [owner for owner, (uid, username) in parsed.items() if users.get(uid) == username]})
