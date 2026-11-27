import time

import jwt
from django.db import transaction
from django.db.models import F
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from app.chatgpt.models import ChatgptAccount, ChatgptCar
from app.chatgpt.serializers import ShowChatgptTokenSerializer, AddChatgptTokenSerializer, ChatGPTLoginSerializer, \
    UpdateChatgptInfoSerializer, DeleteChatgptAccountSerializer, CheckChatgptTokenExpirySerializer, \
    RefreshChatgptTokenSerializer, ResetChatgptLoginCountSerializer
from app.page import DefaultPageNumberPagination
from app.settings import CHATGPT_GATEWAY_URL
from app.utils import get_request_subject, save_visit_log, req_gateway
from app.accounts.models import User
from app.accounts.session_authority import gateway_authorization, capability_aliases, account_model_policy
from app.accounts.views.announcements import active_login_block_for
from app.chatgpt.views.web_login import apply_web_credentials, refresh_pool_credentials
from rest_framework.exceptions import PermissionDenied, ValidationError

DEFAULT_REFRESH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"


def build_token_expiry_result(account, now=None, error=""):
    now = now or int(time.time())
    exp = None
    iat = None
    try:
        payload = jwt.decode(account.access_token, options={"verify_signature": False})
        exp = payload.get("exp")
        iat = payload.get("iat")
    except Exception as exc:
        error = error or str(exc)

    remaining_seconds = None
    expired = None
    if type(exp) is int:
        expired = exp <= now
        if account.access_token_valid:
            remaining_seconds = exp - now
    if not account.access_token_valid:
        exp = None
        iat = None

    return {
        "id": account.id,
        "chatgpt_username": account.chatgpt_username,
        "access_token_exp": exp,
        "access_token_iat": iat,
        "remaining_seconds": remaining_seconds,
        "supported_login_modes": (["api"] if account.access_token_valid else []) + (["web"] if account.session_token_valid else []),
        "expired": expired,
        "access_token_valid": account.access_token_valid,
        "session_token_valid": account.session_token_valid,
        "last_check_at": account.last_check_at,
        "last_error": account.last_error or error,
        "has_refresh_token": bool(account.refresh_token),
    }


class ChatGPTAccountEnum(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        result = ChatgptAccount.objects.filter(auth_status=True).order_by("-id").values(
            "id", "chatgpt_username", "plan_type").all()
        return Response({"data": result})


class ChatGPTAccountView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request, *args, **kwargs):
        queryset = ChatgptAccount.objects.order_by("-id").all()
        query = str(request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(chatgpt_username__icontains=query)
        status = request.query_params.get("status")
        if status in ("healthy", "unhealthy"):
            queryset = queryset.filter(auth_status=status == "healthy")
        pg = DefaultPageNumberPagination()
        pg.page_size_query_param = "page_size"
        page_accounts = pg.paginate_queryset(queryset, request=request)
        for account in page_accounts:
            try:
                account.refresh_auth_diagnostics()
            except Exception:
                pass
        serializer = ShowChatgptTokenSerializer(instance=page_accounts, many=True)
        return pg.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs):
        # 录入 chatgpt 账号
        serializer = AddChatgptTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target = ChatgptAccount.objects.filter(pk=data.get("account_id")).first() if data.get("account_id") else None
        if data.get("account_id") and target is None:
            raise ValidationError("原账号已删除，请重新载入")
        if target and target.web_identity_id:
            raise ValidationError("该账号由自动化链接维护，请使用一键更新")
        if target and len(data.get("chatgpt_token_list") or []) != 1:
            raise ValidationError("更新账号时请只填写一个 Token")

        if data.get("auth_type") == "refresh_token":
            res_json = req_gateway("post", "/api/get-user-info", json={
                "auth_type": "refresh_token",
                "client_id": data["client_id"].strip(),
                "refresh_token": data["refresh_token"].strip(),
            })
            self.ensure_manual_credentials(res_json)
            if target and target.chatgpt_username.casefold() != str((res_json.get("user_info") or {}).get("email") or "").casefold():
                raise ValidationError("Token 不属于待更新账号")
            res_json["auth_status"] = True
            ChatgptAccount.save_data(res_json)
            chatgpt_name = res_json["user_info"]["email"]
            req_gateway("post", "/api/close-chatgpt-memory", json={"chatgpt_name": chatgpt_name})
            return Response({"message": "录入成功"})

        for chatgpt_token in data["chatgpt_token_list"]:
            if not chatgpt_token:
                continue
            res_json = req_gateway("post", "/api/get-user-info", json={"chatgpt_token": chatgpt_token})
            self.ensure_manual_credentials(res_json)
            if target and target.chatgpt_username.casefold() != str((res_json.get("user_info") or {}).get("email") or "").casefold():
                raise ValidationError("Token 不属于待更新账号")
            res_json["auth_status"] = True
            ChatgptAccount.save_data(res_json)

            # 关闭记忆
            chatgpt_name = res_json["user_info"]["email"]
            req_gateway("post", "/api/close-chatgpt-memory", json={"chatgpt_name": chatgpt_name})

        return Response({"message": "录入成功"})

    @staticmethod
    def ensure_manual_credentials(data):
        email = (data.get("user_info") or {}).get("email") or ""
        if ChatgptAccount.objects.filter(chatgpt_username__iexact=email, web_identity_id__isnull=False).exclude(web_identity_id="").exists():
            raise ValidationError("此账号由官网连接维护，请先解除连接再手动录入")

    def put(self, request):
        serializer = UpdateChatgptInfoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = ChatgptAccount.objects.filter(chatgpt_username=data["chatgpt_username"]).first()
        if account and account.web_identity_id:
            result = req_gateway("post", "/api/web-login", json={
                "action": "configure-pool", "owner": get_request_subject(request),
                "authorization": gateway_authorization(request), "id": account.web_identity_id,
                "proxy_node_id": data.get("proxy_node_id"),
            })
            apply_web_credentials(account, result)
        ChatgptAccount.objects.filter(chatgpt_username=data["chatgpt_username"]).update(
            remark=data.get("remark") or "",
            proxy_node_id=data.get("proxy_node_id"),
        )
        return Response({"message": "更新gpt信息成功"})

    def delete(self, request):
        serializer = DeleteChatgptAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gpt_obj = ChatgptAccount.objects.filter(chatgpt_username=serializer.data["chatgpt_username"]).first()
        if gpt_obj:
            from app.chatgpt.account_lifecycle import delete_upstream_account
            delete_upstream_account(request, gpt_obj)

        return Response({"message": "删除成功"})


class ChatGPTTokenExpiryView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        serializer = CheckChatgptTokenExpirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queryset = ChatgptAccount.objects.order_by("-id").all()
        ids = serializer.data.get("ids") or []
        if ids:
            queryset = queryset.filter(id__in=ids)

        now = int(time.time())
        results = []
        for account in queryset:
            error = ""

            try:
                account.refresh_auth_diagnostics(force=True)
            except Exception as exc:
                if not error:
                    error = str(exc)

            results.append(build_token_expiry_result(account, now=now, error=error))

        return Response({"results": results})


class ChatGPTRefreshTokenView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        serializer = RefreshChatgptTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        managed = ChatgptAccount.objects.filter(id=serializer.validated_data["id"]).first()
        if managed is None:
            raise ValidationError("账号不存在")
        if managed and managed.web_identity_id:
            try:
                result = req_gateway("post", "/api/web-login", json={
                    "action": "renew-pool", "pool": True, "id": managed.web_identity_id,
                    "owner": get_request_subject(request), "authorization": gateway_authorization(request),
                }, timeout=(10, 135))
            except ValidationError:
                # The interactive flow remains available after a failed
                # automatic attempt; existing credentials stay untouched.
                result = {"status": "reauth_required"}
            if result.get("status") != "renewed":
                return Response({"status": "reauth_required", "connection_id": managed.web_identity_id,
                                 "message": "未取得新的 Session 和 AccessToken，请完成官网登录"})
            credentials = result.get("credentials") or {}
            # Rust checks identity, expiry and both token values before success.
            apply_web_credentials(managed, credentials, touch_modified=True)
            return Response({"status": "renewed", "message": "Session 和 AccessToken 已更新",
                             "result": build_token_expiry_result(managed)})

        if serializer.validated_data.get("force_web") or not managed.refresh_token:
            return Response({"status": "manual_required", "account_id": managed.pk,
                             "message": "该账号为手动录入，请填写新的 Token"})

        with transaction.atomic():
            account = ChatgptAccount.objects.select_for_update().filter(id=serializer.data["id"]).first()
            if not account:
                raise ValidationError("账号不存在")
            if not account.refresh_token:
                raise ValidationError("该账号没有 refresh_token，无法立即刷新")

            res_json = req_gateway("post", "/api/get-user-info", json={
                "auth_type": "refresh_token",
                "client_id": account.refresh_client_id or DEFAULT_REFRESH_CLIENT_ID,
                "refresh_token": account.refresh_token,
            })
            res_json["auth_status"] = True
            refreshed_id = ChatgptAccount.save_data(res_json)
            refreshed = ChatgptAccount.objects.get(id=refreshed_id)

        return Response({
            "message": "刷新成功",
            "result": build_token_expiry_result(refreshed),
        })


class ChatGPTLoginView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        if active_login_block_for(request.user):
            raise PermissionDenied("公告生效期间，暂不能进入 ChatGPT")
        serializer = ChatGPTLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_gpt_list = ChatgptAccount.get_for_user(request.user)
        user_gpt_list = list(user_gpt_list)
        for account in user_gpt_list:
            if account.web_identity_id:
                try:
                    refresh_pool_credentials(request, account)
                except ValidationError:
                    # One unavailable upstream must not prevent selecting another account.
                    try:
                        fresh = jwt.decode(account.access_token, options={"verify_signature": False}).get("exp", 0) > int(time.time())
                    except Exception:
                        fresh = False
                    if not fresh:
                        account.access_token_valid = account.session_token_valid = False
        user_gpt_id_list = [i.id for i in user_gpt_list]

        login_mode = serializer.data.get("login_mode", "api")
        chatgpt_id = serializer.validated_data.get("chatgpt_id")
        if chatgpt_id is not None and chatgpt_id not in user_gpt_id_list:
            raise ValidationError("该账号不属于当前用户")

        if chatgpt_id is None:
            candidates = [
                item for item in user_gpt_list
                if item.auth_status and (
                    (login_mode == "api" and item.access_token_valid)
                    or (login_mode == "web" and item.session_token_valid)
                )
            ]
            if not candidates:
                raise ValidationError("账号池中没有可用上游账号")
            def load_key(item):
                used = (item.usage_snapshot or {}).get("used_percent")
                fresh = item.usage_checked_at and int(time.time()) - item.usage_checked_at <= 7200
                return (used if fresh and isinstance(used, (int, float)) else 50, item.login_count, item.id)
            chatgpt = min(candidates, key=load_key)
        else:
            chatgpt = next(item for item in user_gpt_list if item.id == chatgpt_id)

        if login_mode == "api" and not chatgpt.access_token_valid:
            raise ValidationError("该账号当前不支持 API 模式，请联系管理员更新 AccessToken")
        if login_mode == "web" and not chatgpt.session_token_valid:
            raise ValidationError("该账号当前不支持 Web 模式，请联系管理员更新 SessionToken")

        user_name = get_request_subject(request)
        payload = {
            "web_identity_id": chatgpt.web_identity_id,
            "user_name": user_name,
            "authorization": gateway_authorization(request),
            "access_token": chatgpt.access_token,
            "session_token": chatgpt.session_token,
            "extra_cookies": chatgpt.extra_cookies,
            "login_mode": login_mode,
            "isolated_session": request.user.isolated_session,
            "mcp_isolation": request.user.mcp_isolation and request.user.capability_policy_initialized,
            "skills_isolation": request.user.skills_isolation and request.user.capability_policy_initialized,
            "mcp_allowed_ids": capability_aliases(request.user, "mcp_allowlist"),
            "skills_allowed_ids": capability_aliases(request.user, "skills_allowlist"),
            "limits": [
                item for item in (request.user.model_limit or []) if isinstance(item, str)
            ],
            "proxy_node_id": chatgpt.proxy_node_id,
            "daily_quota": request.user.daily_quota,
            "monthly_quota": request.user.monthly_quota,
            "force_chat_mode": request.user.force_chat_mode,
            "hide_chat_work_toggle": request.user.hide_chat_work_toggle,
            "hide_library": request.user.hide_library,
            "hide_suggestions": request.user.hide_suggestions,
        }
        payload.update(account_model_policy(request.user, chatgpt))
        res_json = req_gateway("post", "/api/login", json=payload)

        ChatgptAccount.objects.filter(id=chatgpt.id).update(login_count=F("login_count") + 1)

        save_visit_log(request, "choose-gpt", chatgpt.chatgpt_username)

        return Response(res_json)


class ChatGPTLoginCountResetView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        serializer = ResetChatgptLoginCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = ChatgptAccount.objects.filter(id=serializer.validated_data["id"]).update(login_count=0)
        if not updated:
            raise ValidationError("账号不存在")
        return Response({"message": "被登录次数已重置"})
