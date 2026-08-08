import time
import hashlib

import requests
from django.conf import settings
from django.db import transaction
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from requests.exceptions import RequestException
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from app.accounts.models import User
from app.accounts.authentication import clear_auth_cookie, set_auth_cookie
from app.accounts.serializers import UserRegisterSerializer
from app.chatgpt.models import ChatgptAccount
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME
from app.settings import ALLOW_REGISTER, TURNSTILE_ENABLED, TURNSTILE_SECRET_KEY
from app.utils import get_client_ip, get_request_subject, issue_free_session, save_visit_log, req_gateway


TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(request, expected_action):
    if not TURNSTILE_ENABLED:
        return

    token = str(request.data.get("turnstile_token") or "").strip()
    if not token:
        raise ValidationError({"message": "请完成人机验证"})

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": get_client_ip(request),
            },
            timeout=5,
        )
        result = response.json()
    except (RequestException, ValueError):
        raise ValidationError({"message": "人机验证服务暂时不可用，请稍后重试"})

    if not result.get("success") or result.get("action") != expected_action:
        raise ValidationError({"message": "人机验证无效或已过期，请重新验证"})


class LoginIpRateThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_cache_key(self, request, view):
        digest = hashlib.sha256(self.get_ident(request).encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class LoginAccountRateThrottle(SimpleRateThrottle):
    scope = "login_account"

    def get_cache_key(self, request, view):
        username = str(request.data.get("username") or "").strip().lower()
        if not username:
            return None
        digest = hashlib.sha256(username.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


def issue_user_token(user, *, rotate=False):
    if rotate:
        Token.objects.filter(user=user).delete()
        return Token.objects.create(user=user)
    token, _ = Token.objects.get_or_create(user=user)
    return token


class UserFreeLoginView(APIView):
    authentication_classes = ()
    throttle_classes = (LoginIpRateThrottle,)

    def post(self, request):
        verify_turnstile(request, "login")
        user = User.objects.filter(username=FREE_ACCOUNT_USERNAME, is_active=True).first()
        if not user:
            raise ValidationError({"message": "当前系统无免费账号可用"})
        request.user = user

        token = issue_user_token(user)
        save_visit_log(request, "login")

        rotate_token(request)
        response = Response({
            "authenticated": True,
            "is_admin": False,
            "username": user.username,
            "csrf_token": get_token(request),
        })
        set_auth_cookie(response, token)
        response.set_cookie(
            "free_session",
            issue_free_session(),
            max_age=7 * 24 * 60 * 60,
            httponly=True,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="Strict",
            path="/",
        )
        return response


class AccountLogin(ObtainAuthToken):
    authentication_classes = ()
    throttle_classes = (LoginIpRateThrottle, LoginAccountRateThrottle)

    def post(self, request, *args, **kwargs):
        verify_turnstile(request, "login")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        if user.expired_date and user.expired_date <= timezone.now().date():
            raise ValidationError({"message": "账号已过期"})

        user.last_login = timezone.now()
        user.save()

        token = issue_user_token(user, rotate=True)
        request.user = user

        save_visit_log(request, "login")

        rotate_token(request)
        result = {
            "authenticated": True,
            "username": user.username,
            "csrf_token": get_token(request),
        }
        if user.is_staff or user.is_superuser:
            result.update({"is_admin": True})
        response = Response(result)
        set_auth_cookie(response, token)
        return response


class AccountLogout(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        user_name = get_request_subject(request)
        try:
            req_gateway("post", "/api/logout", json={"user_name": user_name})
        except ValidationError:
            pass

        if request.user.username != FREE_ACCOUNT_USERNAME and request.auth:
            Token.objects.filter(key=str(request.auth)).delete()

        response = Response({"message": "退出成功"})
        response.delete_cookie("free_session", path="/", samesite="Strict")
        clear_auth_cookie(response)
        return response


class AccountRegister(APIView):
    authentication_classes = ()
    throttle_classes = (LoginIpRateThrottle, LoginAccountRateThrottle)
    def post(self, request, *args, **kwargs):
        verify_turnstile(request, "register")

        if not ALLOW_REGISTER:
            raise ValidationError({"message": "当前系统禁止注册账号"})

        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data["username"] == ADMIN_USERNAME:
            raise ValidationError({"message": "该用户名不可注册"})
        if User.objects.filter(username=data["username"]).exists():
            raise ValidationError({"message": "账号已存在"})

        res_json = req_gateway("post", "/api/get-user-info", json={"chatgpt_token": data["chatgpt_token"]})

        from app.chatgpt.models import ChatgptCar
        with transaction.atomic():
            chatgptaccount_id = ChatgptAccount.save_data(res_json)
            chatgptcar = ChatgptCar.objects.create(
                car_name=f"reg_{data['username']}",
                gpt_account_list=[chatgptaccount_id],
                created_time=int(time.time()),
                updated_time=int(time.time()),
                remark="用户注册时，系统自动创建",
            )
            user = User.objects.create_user(
                username=data["username"],
                password=data["password"],
                last_login=timezone.now(),
                gptcar_list=[chatgptcar.id],
            )

        token = issue_user_token(user, rotate=True)
        rotate_token(request)
        response = Response({
            "authenticated": True,
            "is_admin": False,
            "username": user.username,
            "csrf_token": get_token(request),
        })
        set_auth_cookie(response, token)
        return response
