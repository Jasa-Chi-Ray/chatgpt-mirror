import time
import hashlib
import secrets
from datetime import timedelta

import requests
from django.conf import settings
from django.db import transaction
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from requests.exceptions import RequestException
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from app.accounts.models import User, PendingLogin, VisitorSession
from app.accounts.authentication import AUTH_COOKIE_NAME, ExpiringCookieTokenAuthentication, clear_auth_cookie, set_auth_cookie
from app.accounts.session_authority import digest
from django.core import signing
from django.utils.crypto import constant_time_compare
from app.accounts.serializers import UserRegisterSerializer
from app.chatgpt.models import ChatgptAccount
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME
from app.settings import ALLOW_REGISTER, TURNSTILE_ENABLED, TURNSTILE_SECRET_KEY
from app.utils import get_client_ip, get_request_subject, issue_free_session, save_visit_log, req_gateway


TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_TOKEN_MAX_AGE = timedelta(seconds=300)
TURNSTILE_CLOCK_SKEW = timedelta(seconds=30)


def verify_turnstile(request, expected_action):
    if not TURNSTILE_ENABLED:
        return timezone.now() + timedelta(seconds=60)

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
        response.raise_for_status()
        result = response.json()
    except (RequestException, ValueError):
        raise ValidationError({"message": "人机验证服务暂时不可用，请稍后重试"})

    if not isinstance(result, dict) or result.get("success") is not True:
        raise ValidationError({"message": "人机验证无效或已过期，请重新验证"})
    if result.get("action") != expected_action:
        raise ValidationError({"message": "人机验证无效或已过期，请重新验证"})

    try:
        challenge_time = parse_datetime(str(result.get("challenge_ts") or ""))
    except ValueError:
        challenge_time = None
    if challenge_time is None or timezone.is_naive(challenge_time):
        raise ValidationError({"message": "人机验证无效或已过期，请重新验证"})
    token_age = timezone.now() - challenge_time
    if token_age < -TURNSTILE_CLOCK_SKEW or token_age > TURNSTILE_TOKEN_MAX_AGE:
        raise ValidationError({"message": "人机验证无效或已过期，请重新验证"})
    return min(timezone.now() + timedelta(seconds=60), challenge_time + TURNSTILE_TOKEN_MAX_AGE)


def pending_login(request, user, expires_at, *, visitor=False):
    raw = secrets.token_urlsafe(32)
    get_token(request)
    PendingLogin.objects.filter(expires_at__lte=timezone.now()).delete()
    PendingLogin.objects.create(
        digest=digest(raw), user=user, expires_at=expires_at, visitor=visitor,
        password_digest=digest(user.password), csrf_digest=digest(request.META["CSRF_COOKIE"]),
    )
    return Response({"authenticated": False, "login_ticket": raw})


class LoginIpRateThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_cache_key(self, request, view):
        # The gateway overwrites this address and Django is an internal service.
        digest = hashlib.sha256(get_client_ip(request).encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class LoginAccountRateThrottle(SimpleRateThrottle):
    scope = "login_account"

    def get_cache_key(self, request, view):
        username = str(request.data.get("username") or "").strip().lower()
        if not username:
            return None
        digest = hashlib.sha256(username.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class LoginConfirmRateThrottle(LoginIpRateThrottle):
    scope = "login_confirm"


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
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        expires_at = verify_turnstile(request, "login")
        user = User.objects.filter(username=FREE_ACCOUNT_USERNAME, is_active=True).first()
        if not user:
            raise ValidationError({"message": "当前系统无免费账号可用"})
        return pending_login(request, user, expires_at, visitor=True)


class AccountLogin(ObtainAuthToken):
    authentication_classes = ()
    throttle_classes = (LoginIpRateThrottle, LoginAccountRateThrottle)

    def post(self, request, *args, **kwargs):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        expires_at = verify_turnstile(request, "login")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']
        if user.expired_date and user.expired_date <= timezone.now().date():
            raise ValidationError({"message": "账号已过期"})

        return pending_login(request, user, expires_at)


class ConfirmLogin(APIView):
    authentication_classes = ()
    throttle_classes = (LoginConfirmRateThrottle,)

    def post(self, request):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        with transaction.atomic():
            ticket = PendingLogin.objects.select_related("user").filter(
                digest=digest(request.data.get("login_ticket", "")), expires_at__gt=timezone.now(),
            ).first()
            if (not ticket or not constant_time_compare(
                    ticket.csrf_digest, digest(request.META.get("CSRF_COOKIE", "")))):
                raise ValidationError({"message": "登录确认已失效，请重新验证"})
            user = ticket.user
            if (not user.is_active or
                    (user.expired_date and user.expired_date <= timezone.localdate()) or
                    ticket.password_digest != digest(user.password)):
                raise ValidationError({"message": "账号状态已改变，请重新登录"})
            claimed, _ = PendingLogin.objects.filter(pk=ticket.pk).delete()
            if not claimed:
                raise ValidationError({"message": "登录确认已使用"})
            if ticket.visitor:
                # Expired shared tokens must not be reissued to a new visitor.
                Token.objects.filter(user=user, created__lte=timezone.now() - timedelta(
                    seconds=settings.API_TOKEN_TTL_SECONDS,
                )).delete()
            token = issue_user_token(user, rotate=not ticket.visitor)
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])
            request.user = user
            save_visit_log(request, "login")
            rotate_token(request)
            response = Response({
                "authenticated": True, "username": user.username,
                "is_admin": user.is_staff or user.is_superuser,
                "csrf_token": get_token(request),
            })
            set_auth_cookie(response, token)
            if ticket.visitor:
                response.set_cookie(
                    "free_session", issue_free_session(), max_age=7 * 24 * 60 * 60,
                    httponly=True, secure=settings.SESSION_COOKIE_SECURE,
                    samesite="Strict", path="/",
                )
            return response


class AccountLogout(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        raw = request.COOKIES.get(AUTH_COOKIE_NAME, "")
        authorization = request.headers.get("Authorization", "").split()
        if len(authorization) == 2 and authorization[0].lower() == "token":
            raw = authorization[1]
        token = Token.objects.select_related("user").filter(key=raw).first()
        subject = None
        if token:
            user = token.user
            if user.username == FREE_ACCOUNT_USERNAME:
                from app.utils import FREE_SESSION_SALT
                try:
                    sid = signing.loads(request.COOKIES.get("free_session", ""), salt=FREE_SESSION_SALT)["sid"]
                    VisitorSession.objects.filter(sid=sid, user=user).delete()
                    subject = f"{user.username}:{sid}"
                except (signing.BadSignature, KeyError, TypeError):
                    pass
            else:
                subject = user.username
                token.delete()
                PendingLogin.objects.filter(user=user).delete()
        from app.accounts.models import GatewayRevocation
        cleanup_pending = bool(subject and GatewayRevocation.objects.filter(subject=subject).exists())
        response = Response({"message": "退出成功", "gateway_cleanup_pending": cleanup_pending})
        response.delete_cookie("free_session", path="/", samesite="Strict")
        clear_auth_cookie(response)
        return response


class AccountRegister(APIView):
    authentication_classes = ()
    throttle_classes = (LoginIpRateThrottle, LoginAccountRateThrottle)
    def post(self, request, *args, **kwargs):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        expires_at = verify_turnstile(request, "register")

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

        return pending_login(request, user, expires_at)
