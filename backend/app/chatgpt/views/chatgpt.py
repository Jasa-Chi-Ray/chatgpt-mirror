import time

import jwt
from django.db import transaction
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from app.chatgpt.models import ChatgptAccount, ChatgptCar
from app.chatgpt.serializers import ShowChatgptTokenSerializer, AddChatgptTokenSerializer, ChatGPTLoginSerializer, \
    UpdateChatgptInfoSerializer, DeleteChatgptAccountSerializer, CheckChatgptTokenExpirySerializer, \
    RefreshChatgptTokenSerializer
from app.page import DefaultPageNumberPagination
from app.settings import CHATGPT_GATEWAY_URL
from app.utils import save_visit_log, req_gateway, get_client_ip
from app.accounts.models import User
from rest_framework.exceptions import ValidationError

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
    expired = True
    if isinstance(exp, int):
        remaining_seconds = exp - now
        expired = remaining_seconds <= 0

    return {
        "id": account.id,
        "chatgpt_username": account.chatgpt_username,
        "access_token_exp": exp,
        "access_token_iat": iat,
        "remaining_seconds": remaining_seconds,
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
        pg = DefaultPageNumberPagination()
        pg.page_size_query_param = "page_size"
        page_accounts = pg.paginate_queryset(queryset, request=request)
        for account in page_accounts:
            try:
                account.refresh_auth_diagnostics()
            except Exception:
                pass
        chatgpt_list = [i.chatgpt_username for i in page_accounts]

        try:
            use_count_dict = req_gateway("post", "/api/get-chatgpt-use-count", json={"chatgpt_list": chatgpt_list})
        except:
            use_count_dict = {}
        serializer = ShowChatgptTokenSerializer(instance=page_accounts, use_count_dict=use_count_dict, many=True)
        return pg.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs):
        # 录入 chatgpt 账号
        serializer = AddChatgptTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("auth_type") == "refresh_token":
            res_json = req_gateway("post", "/api/get-user-info", json={
                "auth_type": "refresh_token",
                "client_id": data["client_id"].strip(),
                "refresh_token": data["refresh_token"].strip(),
            })
            res_json["auth_status"] = True
            ChatgptAccount.save_data(res_json)
            chatgpt_name = res_json["user_info"]["email"]
            req_gateway("post", "/api/close-chatgpt-memory", json={"chatgpt_name": chatgpt_name})
            return Response({"message": "录入成功"})

        for chatgpt_token in data["chatgpt_token_list"]:
            if not chatgpt_token:
                continue
            res_json = req_gateway("post", "/api/get-user-info", json={"chatgpt_token": chatgpt_token})
            res_json["auth_status"] = True
            ChatgptAccount.save_data(res_json)

            # 关闭记忆
            chatgpt_name = res_json["user_info"]["email"]
            req_gateway("post", "/api/close-chatgpt-memory", json={"chatgpt_name": chatgpt_name})

        return Response({"message": "录入成功"})

    def put(self, request):
        serializer = UpdateChatgptInfoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
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
            car_obj = ChatgptCar.objects.filter(gpt_account_list=[gpt_obj.id], car_name__contains="reg_").first()
            if car_obj:
                User.objects.filter(gptcar_list=[car_obj.id]).delete()
                car_obj.delete()
            gpt_obj.delete()

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
        serializer = ChatGPTLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ip = get_client_ip(request)

        user_gpt_list = ChatgptAccount.get_by_gptcar_list(request.user.gptcar_list)
        user_gpt_id_list = [i.id for i in user_gpt_list]

        if serializer.data["chatgpt_id"] not in user_gpt_id_list:
            raise ValidationError("该账号不属于当前用户")

        chatgpt = ChatgptAccount.get_by_id(serializer.data["chatgpt_id"])
        login_mode = serializer.data.get("login_mode", "api")

        if login_mode == "api" and not chatgpt.access_token_valid:
            raise ValidationError("该账号当前不支持 API 模式，请联系管理员更新 AccessToken")
        if login_mode == "web" and not chatgpt.session_token_valid:
            raise ValidationError("该账号当前不支持 Web 模式，请联系管理员更新 SessionToken")

        user_name = request.user.username + ip if request.user.username == "free_account" else request.user.username
        payload = {
            "user_name": user_name,
            "access_token": chatgpt.access_token,
            "session_token": chatgpt.session_token,
            "extra_cookies": chatgpt.extra_cookies,
            "login_mode": login_mode,
            "isolated_session": request.user.isolated_session,
            "limits": request.user.model_limit,
            "proxy_node_id": chatgpt.proxy_node_id,
        }
        # print(payload)
        res_json = req_gateway("post", "/api/login", json=payload)

        save_visit_log(request, "choose-gpt", chatgpt.chatgpt_username)

        return Response(res_json)
