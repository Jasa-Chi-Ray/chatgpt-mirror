import time

from django.db.models import Q
from django.utils import timezone
from django.middleware.csrf import get_token, rotate_token
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import User, VisitLog, PendingLogin, VisitorSession
from app.accounts.session_authority import gateway_authorization, capability_aliases
from app.accounts.serializers import ShowVisitLogModelSerializer, AddUserAccountSerializer, UserBindChatGPTSerializer, \
    ShowUserAccountModelSerializer, BatchModelLimitSerializer, BatchUserActionSerializer, ChangePasswordSerializer
from app.accounts.serializers import ConversationTitlePrivacySerializer
from app.accounts.serializers import UserCapabilityPolicySerializer
from app.accounts.authentication import set_auth_cookie
from rest_framework.authtoken.models import Token
from app.chatgpt.models import ChatgptAccount
from app.page import DefaultPageNumberPagination
from app.permissions import IsSuperUser
from app.settings import ADMIN_USERNAME
from app.utils import get_request_subject, req_gateway
from app.accounts.views.login import issue_user_token


def revoke_user_sessions(user, *, require_gateway=False):
    Token.objects.filter(user=user).delete()
    PendingLogin.objects.filter(user=user).delete()
    VisitorSession.objects.filter(user=user).delete()
    from app.accounts.models import GatewayRevocation
    if require_gateway and GatewayRevocation.objects.filter(subject=user.username).exists():
        raise ValidationError("会话已在管理端撤销，网关通知正在自动重试；旧授权最迟在 60 分钟内失效")


def quota_snapshot(user):
    now = timezone.now()
    day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    month_start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    daily_used = VisitLog.objects.filter(
        username=user.username, log_type="proxy", created_at__gte=day_start
    ).count()
    monthly_used = VisitLog.objects.filter(
        username=user.username, log_type="proxy", created_at__gte=month_start
    ).count()
    try:
        remote = req_gateway("post", "/api/get-user-quota-usage", json={
            "user_name": get_request_subject_from_user(user),
            "day_start": day_start,
            "month_start": month_start,
        })
        daily_used = int(remote.get("daily_used", daily_used))
        monthly_used = int(remote.get("monthly_used", monthly_used))
    except ValidationError:
        pass
    return {
        "daily": {"limit": user.daily_quota, "used": daily_used},
        "monthly": {"limit": user.monthly_quota, "used": monthly_used},
    }


def get_request_subject_from_user(user):
    return user.username


def normalized_model_limits(user):
    return [item for item in (user.model_limit or []) if isinstance(item, str)]


class GetMirrorToken(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        user = request.user

        user_gpt_list = ChatgptAccount.get_by_gptcar_list(user.gptcar_list)
        chatgpt_username_list = [i.chatgpt_username for i in user_gpt_list]
        res = req_gateway("post", "/api/get-mirror-token", json={
            "isolated_session": user.isolated_session,
            "mcp_isolation": user.mcp_isolation and user.capability_policy_initialized,
            "skills_isolation": user.skills_isolation and user.capability_policy_initialized,
            "mcp_allowed_ids": capability_aliases(user, "mcp_allowlist"),
            "skills_allowed_ids": capability_aliases(user, "skills_allowlist"),
            "limits": normalized_model_limits(user),
            "chatgpt_list": chatgpt_username_list,
            "user_name": get_request_subject(request),
            "authorization": gateway_authorization(request),
            "daily_quota": user.daily_quota,
            "monthly_quota": user.monthly_quota,
            "force_chat_mode": user.force_chat_mode,
        })
        for line in res:
            obj = ChatgptAccount.objects.filter(chatgpt_username=line["chatgpt_username"]).first()
            if obj:
                line["auth_status"] = obj.auth_status
                line["plan_type"] = obj.plan_type
        return Response(res)


class UserChatGPTAccountList(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        results = []
        user_gpt_list = ChatgptAccount.get_by_gptcar_list(request.user.gptcar_list)
        for account in user_gpt_list:
            try:
                account.refresh_auth_diagnostics()
            except Exception:
                pass
        auth_user_gpt_list = [i for i in user_gpt_list if i.auth_status]

        for line in auth_user_gpt_list or user_gpt_list:
            supported_login_modes = []
            if line.access_token_valid:
                supported_login_modes.append("api")
            if line.session_token_valid:
                supported_login_modes.append("web")
            results.append({
                "id": line.id,
                "login_count": line.login_count,
                "chatgpt_flag": "{:03}{}".format(line.id, line.chatgpt_username[:3]),
                "plan_type": line.plan_type,
                "auth_status": line.auth_status,
                "access_token_valid": line.access_token_valid,
                "session_token_valid": line.session_token_valid,
                "supported_login_modes": supported_login_modes,
                "default_login_mode": "api" if line.access_token_valid else "web",
            })

        return Response({"results": results})


class BatchModelLimit(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        serializer = BatchModelLimitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for user in User.objects.filter(id__in=serializer.data["user_id_list"]):
            user.model_limit = serializer.data["model_limit"]
            user.save(update_fields=["model_limit"])
        return Response({"message": "更新成功"})


class MirrorProxyConfigView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def get(self, request):
        return Response(req_gateway("get", "/api/mirror-proxy-config"))

    def post(self, request):
        enabled = request.data.get("enabled")
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        return Response(req_gateway("post", "/api/mirror-proxy-config", json={
            "transport_mode": request.data.get("transport_mode") or "reqwest",
            "enabled": bool(enabled),
            "proxy_url": request.data.get("proxy_url"),
            "username": request.data.get("username"),
            "password": request.data.get("password"),
            "nodes": request.data.get("nodes") or [],
        }))


class MirrorProxyTestView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def post(self, request):
        enabled = request.data.get("enabled")
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        return Response(req_gateway("post", "/api/test-mirror-proxy-config", json={
            "transport_mode": request.data.get("transport_mode") or "reqwest",
            "enabled": bool(enabled),
            "proxy_url": request.data.get("proxy_url"),
            "username": request.data.get("username"),
            "password": request.data.get("password"),
            "nodes": request.data.get("nodes") or [],
        }))


class CustomScriptConfigView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def get(self, request):
        return Response(req_gateway("get", "/api/custom-scripts"))

    def post(self, request):
        return Response(req_gateway("post", "/api/custom-scripts", json={
            "scripts": request.data.get("scripts") or [],
            "trusted_cdn_sources": request.data.get("trusted_cdn_sources") or [],
        }))


class UserRelateGPTCarView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request, *args, **kwargs):
        serializer = UserBindChatGPTSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        for user_id in serializer.data["user_id_list"]:
            user = User.objects.filter(id=user_id).first()
            user.gptcar_list = serializer.data["gptcar_id_list"]
            user.save()

        return Response({"message": "绑定成功"})


class UserAccountView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request, *args, **kwargs):
        queryset = User.objects.order_by("-id").all()
        query = str(request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(Q(username__icontains=query) | Q(remark__icontains=query))
        status = request.query_params.get("status")
        if status in ("active", "inactive"):
            queryset = queryset.filter(is_active=status == "active")
        pg = DefaultPageNumberPagination()
        pg.page_size_query_param = "page_size"
        page_accounts = pg.paginate_queryset(queryset, request=request)
        username_list = [i.username for i in page_accounts]
        try:
            use_count_dict = req_gateway("post", "/api/get-user-use-count", json={"username_list": username_list})
        except:
            use_count_dict = {}
        try:
            conversation_stats_dict = req_gateway(
                "post",
                "/api/conversation-statistics",
                json={"user_name_list": username_list},
            )
        except ValidationError:
            conversation_stats_dict = {}
        serializer = ShowUserAccountModelSerializer(
            instance=page_accounts,
            use_count_dict=use_count_dict,
            conversation_stats_dict=conversation_stats_dict,
            many=True,
        )
        return pg.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs):
        # 添加或更新用户
        serializer = AddUserAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["username"] == ADMIN_USERNAME:
            raise ValidationError({"message": "管理员账号不能操作"})

        user = User.objects.filter(username=data["username"]).first()
        created = user is None
        if created:
            if not data.get("password"):
                raise ValidationError({"password": "新增用户必须设置密码"})
            user = User(username=data["username"])

        if data.get("password"):
            user.set_password(data["password"])

        if "expired_date" in data:
            user.expired_date = data["expired_date"]

        user.gptcar_list = data["gptcar_list"]
        user.is_active = data["is_active"]
        user.model_limit = data["model_limit"]
        user.isolated_session = data["isolated_session"]
        user.mcp_isolation = data.get("mcp_isolation", True)
        user.skills_isolation = data.get("skills_isolation", True)
        user.remark = data["remark"]
        user.daily_quota = data.get("daily_quota", 0)
        user.monthly_quota = data.get("monthly_quota", 0)
        if "force_chat_mode" in data:
            user.force_chat_mode = data["force_chat_mode"]
        user.save()

        if "force_chat_mode" in data:
            req_gateway("post", "/api/user-work-mode", json={
                "user_name": user.username,
                "force_chat_mode": user.force_chat_mode,
            })

        credentials_changed = bool(data.get("password"))
        access_revoked = not user.is_active or (
            user.expired_date and user.expired_date <= timezone.localdate()
        )
        if credentials_changed or access_revoked:
            revoke_user_sessions(user)

        return Response({"message": "添加成功"})

    def delete(self, request, *args, **kwargs):
        username = request.data.get("username")
        if username == ADMIN_USERNAME:
            raise ValidationError({"message": "不能删除管理员账号"})
        User.objects.filter(username=username).delete()
        return Response({"message": "删除成功"})


def _user_capability_account(user, account_id):
    account = ChatgptAccount.get_by_gptcar_list(user.gptcar_list).filter(id=account_id).first()
    if not account:
        raise ValidationError({"account_id": "该上游账号不属于此用户当前绑定的账号池"})
    return account


def _capability_grants(items, selected_ids):
    selected = {str(item).strip() for item in selected_ids if str(item).strip()}
    grants = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id not in selected:
            continue
        aliases = []
        for value in item.get("aliases") or []:
            value = str(value or "").strip()
            if value and value != item_id and value not in aliases:
                aliases.append(value)
        grants.append({"id": item_id, "aliases": aliases[:12]})
    return grants


class UserCapabilityPolicyView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def _user(self, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise ValidationError({"user_id": "用户不存在"})
        return user

    def _accounts(self, user):
        return [
            {"id": item.id, "label": f"{item.chatgpt_username} · {item.plan_type}"}
            for item in ChatgptAccount.get_by_gptcar_list(user.gptcar_list)
        ]

    def _discover(self, user, account):
        result = req_gateway("post", "/api/account-capabilities", json={
            "chatgpt_username": account.chatgpt_username,
            "access_token": account.access_token,
            "session_token": account.session_token,
            "extra_cookies": account.extra_cookies,
            "proxy_node_id": account.proxy_node_id,
        })
        if not isinstance(result, dict):
            raise ValidationError("网关返回的能力清单无效")
        return {
            "mcp": [item for item in result.get("mcp", []) if isinstance(item, dict)],
            "skills": [item for item in result.get("skills", []) if isinstance(item, dict)],
        }

    def get(self, request, user_id):
        user = self._user(user_id)
        accounts = self._accounts(user)
        account_id = request.query_params.get("account_id")
        if not account_id:
            return Response({
                "accounts": accounts,
                "selected_account_id": user.capability_account_id,
                "initialized": user.capability_policy_initialized,
                "mcp": [],
                "skills": [],
            })
        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            raise ValidationError({"account_id": "账号 ID 无效"})
        account = _user_capability_account(user, account_id)
        inventory = self._discover(user, account)
        reset_defaults = not user.capability_policy_initialized or user.capability_account_id != account.id
        mcp_allowed = {item.get("id") for item in user.mcp_allowlist if isinstance(item, dict)}
        skills_allowed = {item.get("id") for item in user.skills_allowlist if isinstance(item, dict)}
        for item in inventory["mcp"]:
            item["enabled"] = reset_defaults or item.get("id") in mcp_allowed
        for item in inventory["skills"]:
            item["enabled"] = reset_defaults or item.get("id") in skills_allowed
        return Response({
            "accounts": accounts,
            "selected_account_id": account.id,
            "initialized": user.capability_policy_initialized and not reset_defaults,
            **inventory,
        })

    def post(self, request, user_id):
        user = self._user(user_id)
        serializer = UserCapabilityPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = _user_capability_account(user, serializer.validated_data["account_id"])
        inventory = self._discover(user, account)
        user.capability_account_id = account.id
        user.capability_policy_initialized = True
        user.mcp_allowlist = _capability_grants(
            inventory["mcp"], serializer.validated_data["mcp_allowed_ids"]
        )
        user.skills_allowlist = _capability_grants(
            inventory["skills"], serializer.validated_data["skills_allowed_ids"]
        )
        user.save(update_fields=[
            "capability_account_id", "capability_policy_initialized",
            "mcp_allowlist", "skills_allowlist",
        ])
        return Response({"message": "MCP 与 Skills 权限已保存，用户现有会话已撤销"})

class UserSessionRevokeView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        user_id = request.data.get("user_id")
        if isinstance(user_id, bool):
            raise ValidationError({"user_id": "用户 ID 无效"})
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            raise ValidationError({"user_id": "用户 ID 无效"})

        user = User.objects.filter(id=user_id).first()
        if not user:
            raise ValidationError({"user_id": "用户不存在"})

        revoke_user_sessions(user, require_gateway=True)
        return Response({"message": "会话已撤销，用户将返回登录页面"})


class VisitLogView(generics.ListAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)
    queryset = VisitLog.objects.order_by("-id").all()
    serializer_class = ShowVisitLogModelSerializer
    pagination_class = DefaultPageNumberPagination

    def get_queryset(self):
        queryset = super().get_queryset()
        query = str(self.request.query_params.get("q") or "").strip()
        if query:
            queryset = queryset.filter(
                Q(username__icontains=query) | Q(chatgpt_username__icontains=query)
            )
        log_type = self.request.query_params.get("log_type")
        if log_type:
            queryset = queryset.filter(log_type=log_type)
        return queryset

    def delete(self, request, *args, **kwargs):
        protected_logs = VisitLog.objects.filter(
            username=ADMIN_USERNAME,
            log_type="login",
        )
        protected_count = protected_logs.count()
        deleted_count, _ = VisitLog.objects.exclude(
            username=ADMIN_USERNAME,
            log_type="login",
        ).delete()
        return Response({
            "message": "日志已清除",
            "deleted_count": deleted_count,
            "protected_count": protected_count,
        })


class BatchUserActionView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def post(self, request):
        serializer = BatchUserActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        queryset = User.objects.filter(id__in=serializer.validated_data["user_id_list"]).exclude(
            username=ADMIN_USERNAME
        )
        action = serializer.validated_data["action"]
        users = list(queryset)
        if action == "delete":
            for user in users:
                revoke_user_sessions(user)
            changed, _ = queryset.delete()
        else:
            active = action == "activate"
            changed = len(users)
            for user in users:
                user.is_active = active
                user.save(update_fields=["is_active"])
            if not active:
                for user in users:
                    revoke_user_sessions(user)
        return Response({"message": "批量操作完成", "changed": changed})


class CurrentUserView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response({
            "authenticated": True,
            "username": request.user.username,
            "is_admin": bool(request.user.is_staff or request.user.is_superuser),
            "allow_admin_view_conversation_titles": request.user.allow_admin_view_conversation_titles,
            "quota": quota_snapshot(request.user),
            "csrf_token": get_token(request),
        })


class ConversationTitlePrivacyView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = ConversationTitlePrivacySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.allow_admin_view_conversation_titles = serializer.validated_data[
            "allow_admin_view_conversation_titles"
        ]
        request.user.save(update_fields=["allow_admin_view_conversation_titles"])
        return Response({
            "message": "对话标题隐私设置已保存",
            "allow_admin_view_conversation_titles": request.user.allow_admin_view_conversation_titles,
        })


class UserConversationStatisticsView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get_user(self, user_id):
        user = User.objects.filter(id=user_id).first()
        if not user:
            raise ValidationError("用户不存在")
        return user

    def get(self, request, user_id):
        user = self.get_user(user_id)
        result = req_gateway(
            "post",
            "/api/conversation-statistics",
            json={"user_name": user.username},
        )
        title_visible = bool(user.allow_admin_view_conversation_titles)
        conversations = []
        for item in result.get("conversations") or []:
            conversation_id = str(item.get("conversation_id") or "")
            conversations.append({
                "conversation_id": conversation_id,
                "display_title": (
                    str(item.get("title") or conversation_id)
                    if title_visible
                    else conversation_id
                ),
                "message_count": int(item.get("message_count") or 0),
                "updated_at": item.get("updated_at"),
            })
        result["conversations"] = conversations
        result["title_visible"] = title_visible
        return Response(result)

    def delete(self, request, user_id):
        user = self.get_user(user_id)
        return Response(req_gateway(
            "post",
            "/api/conversation-statistics/reset",
            json={"user_name": user.username},
        ))


class ChangePasswordView(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["current_password"]):
            raise ValidationError({"current_password": "当前密码不正确"})
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        revoke_user_sessions(request.user)
        token = issue_user_token(request.user, rotate=True)
        rotate_token(request)
        response = Response({
            "message": "密码修改成功，其他会话已退出",
            "csrf_token": get_token(request),
        })
        set_auth_cookie(response, token)
        return response


class QuotaView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        return Response(quota_snapshot(request.user))


class OperationsOverviewView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        today_start = int(
            timezone.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        )
        accounts = ChatgptAccount.objects.all()
        try:
            gateway_metrics = req_gateway(
                "post", "/api/operations-overview", json={"day_start": today_start}
            )
        except ValidationError:
            gateway_metrics = {}
        return Response({
            "users": {
                "total": User.objects.count(),
                "active": User.objects.filter(is_active=True).count(),
                "expired": User.objects.filter(expired_date__lte=timezone.localdate()).count(),
            },
            "upstream": {
                "total": accounts.count(),
                "healthy": accounts.filter(auth_status=True).count(),
                "unhealthy": accounts.filter(auth_status=False).count(),
            },
            "activity": {
                "today_logins": VisitLog.objects.filter(
                    log_type="login", created_at__gte=today_start
                ).count(),
                "today_requests": VisitLog.objects.filter(
                    log_type="proxy", created_at__gte=today_start
                ).count() or int(gateway_metrics.get("today_requests", 0)),
                "active_sessions": int(gateway_metrics.get("active_sessions", 0)),
            },
            "generated_at": int(time.time()),
        })
