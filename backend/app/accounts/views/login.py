import time
import hashlib

import requests
from django.contrib.auth import authenticate
from django.conf import settings
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
    throttle_classes = (LoginIpRateThrottle,)

    def post(self, request):
        verify_turnstile(request, "login")
        user = User.objects.filter(username=FREE_ACCOUNT_USERNAME, is_active=True).first()
        if not user:
            raise ValidationError({"message": "当前系统无免费账号可用"})
        request.user = user

        token = issue_user_token(user)
        save_visit_log(request, "login")

        response = Response({"admin_token": token.key})
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

        result = {'admin_token': token.key}
        if user.is_staff or user.is_superuser:
            result.update({"is_admin": True})
        return Response(result)


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
        return response


class AccountRegister(APIView):
    throttle_classes = (LoginIpRateThrottle, LoginAccountRateThrottle)
    def post(self, request, *args, **kwargs):
        verify_turnstile(request, "register")

        if not ALLOW_REGISTER:
            raise ValidationError({"message": "当前系统禁止注册账号"})

        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.data["username"] == ADMIN_USERNAME:
            raise ValidationError({"message": "该用户名不可注册"})

        res_json = req_gateway("post", "/api/get-user-info", json={"chatgpt_token": serializer.data["chatgpt_token"]})
        chatgptaccount_id = ChatgptAccount.save_data(res_json)

        user = User.objects.filter(username=serializer.data["username"]).first()
        if user and not authenticate(username=serializer.data["username"], password=serializer.data["password"]):
            raise ValidationError({"message": "账号已存在"})

        # 创建默认号池
        from app.chatgpt.models import ChatgptCar
        chatgptcar, created = ChatgptCar.objects.get_or_create(
            car_name="reg_{}".format(serializer.data["username"]),
            defaults={
                "created_time": int(time.time()),
                "updated_time": int(time.time()),
                "remark": "用户注册时，系统自动创建"
            })
        gpt_account_list = list(chatgptcar.gpt_account_list)
        gpt_account_list.append(chatgptaccount_id)
        chatgptcar.gpt_account_list = list(set(gpt_account_list))
        chatgptcar.save()

        user, created = User.objects.get_or_create(username=serializer.data["username"])
        user.set_password(serializer.data["password"])
        user.last_login = timezone.now()
        gptcar_list = list(user.gptcar_list)
        gptcar_list.append(chatgptcar.id)
        user.gptcar_list = list(set(gptcar_list))
        user.save()

        token = issue_user_token(user, rotate=True)
        return Response({"admin_token": token.key})
