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
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from app.accounts.models import User, PendingLogin, VisitorSession, LoginSession
from app.accounts.authentication import AUTH_COOKIE_NAME, ExpiringCookieTokenAuthentication, clear_auth_cookie, set_auth_cookie
from app.accounts.login_guard import LoginAdmissionPermission
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


def pending_login(request, user, expires_at, *, visitor=False, oauth_identity=None):
    raw = secrets.token_urlsafe(32)
    get_token(request)
    PendingLogin.objects.filter(expires_at__lte=timezone.now()).delete()
    PendingLogin.objects.create(
        digest=digest(raw), user=user, expires_at=expires_at, visitor=visitor,
        oauth_identity=oauth_identity,
        password_digest=digest(user.password), csrf_digest=digest(request.META["CSRF_COOKIE"]),
    )
    return Response({"authenticated": False, "login_ticket": raw})


class LoginFingerprintRateThrottle(SimpleRateThrottle):
    scope = "login_fingerprint"

    def get_cache_key(self, request, view):
        from app.accounts.login_guard import fingerprint_key, request_fingerprint, valid_api_session
        if valid_api_session(request):
            return None
        ident = fingerprint_key(request_fingerprint(request))
        return self.cache_format % {"scope": self.scope, "ident": ident} if ident else None


class LoginAccountRateThrottle(LoginFingerprintRateThrottle):
    scope = "login_account_fingerprint"

    def get_cache_key(self, request, view):
        renderer = super().get_cache_key(request, view)
        username = str(request.data.get("username") or "").strip().lower()
        if not renderer or not username:
            return None
        digest = hashlib.sha256((renderer + ":" + username).encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class LoginConfirmRateThrottle(LoginFingerprintRateThrottle):
    scope = "login_confirm"


class PasswordAttemptRateThrottle(LoginFingerprintRateThrottle):
    """Limit password checks without throttling existing authenticated page access."""
    scope = "login_account_fingerprint"

    def get_cache_key(self, request, view):
        from app.accounts.login_guard import fingerprint_key, request_fingerprint
        try:
            authenticated = ExpiringCookieTokenAuthentication().authenticate(request)
        except APIException:
            authenticated = None
        ident = ("user:" + str(authenticated[0].pk)) if authenticated else fingerprint_key(request_fingerprint(request))
        return self.cache_format % {"scope": self.scope, "ident": "password-attempt:" + ident} if ident else None


def issue_user_token(user, *, rotate=False):
    if user.can_use_multiple_sessions:
        LoginSession.objects.filter(user=user, created__lte=timezone.now() - timedelta(
            seconds=settings.API_TOKEN_TTL_SECONDS,
        )).delete()
        return LoginSession.objects.create(user=user)
    LoginSession.objects.filter(user=user).delete()
    if rotate:
        Token.objects.filter(user=user).delete()
        return Token.objects.create(user=user)
    token, _ = Token.objects.get_or_create(user=user)
    return token


class UserFreeLoginView(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle,)

    def post(self, request):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        expires_at = verify_turnstile(request, "login")
        user = User.objects.filter(username=FREE_ACCOUNT_USERNAME, is_active=True).first()
        if not user:
            raise ValidationError({"message": "当前系统无免费账号可用"})
        return pending_login(request, user, expires_at, visitor=True)


class AccountLogin(ObtainAuthToken):
    from app.request_parsers import AccessJSONParser, AccessFormParser, AccessMultiPartParser
    parser_classes = (AccessJSONParser, AccessFormParser, AccessMultiPartParser)
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle, LoginAccountRateThrottle, PasswordAttemptRateThrottle)

    def post(self, request, *args, **kwargs):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        expires_at = verify_turnstile(request, "login")
        serializer = self.get_serializer(data=request.data)
        from app.accounts.login_guard import record_failure, reset_failures, LoginCooling, valid_api_session
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            username = str(request.data.get("username") or "").strip()
            password = str(request.data.get("password") or "")
            account = User.objects.filter(username=username).first()
            if username and password and (account is None or not account.check_password(password)):
                seconds = record_failure(request, username)
                if seconds and not valid_api_session(request):
                    raise LoginCooling(seconds)
            raise
        reset_failures(request, str(request.data.get("username") or ""))

        user = serializer.validated_data['user']
        if user.expired_date and user.expired_date <= timezone.now().date():
            raise ValidationError({"message": "账号已过期"})

        return pending_login(request, user, expires_at)


class ConfirmLogin(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
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
            user = User.objects.select_for_update().get(pk=ticket.user_id)
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
            if ticket.visitor:
                token, _ = Token.objects.get_or_create(user=user)
            else:
                token = issue_user_token(user, rotate=True)
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


def revoke_local_login_session(raw, free_session=""):
    # Revoke only the presented local login; the shared upstream token is untouched.
    raw = str(raw or "")
    token_model = LoginSession if len(raw) == 64 else Token
    token = token_model.objects.select_related("user").filter(key=raw).first() if len(raw) in (40, 64) else None
    subject = None
    if token:
        user = token.user
        if user.username == FREE_ACCOUNT_USERNAME:
            from app.utils import FREE_SESSION_SALT
            try:
                sid = signing.loads(free_session or "", salt=FREE_SESSION_SALT)["sid"]
                VisitorSession.objects.filter(sid=sid, user=user).delete()
                subject = f"{user.username}:{sid}"
            except (signing.BadSignature, KeyError, TypeError):
                pass
        else:
            subject = user.username
            token.delete()
            if not isinstance(token, LoginSession):
                PendingLogin.objects.filter(user=user).delete()
    from app.accounts.models import GatewayRevocation
    return bool(subject and GatewayRevocation.objects.filter(subject=subject).exists())


class GatewayLogoutView(APIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = ()

    def post(self, request):
        secret = settings.GATEWAY_ADMIN_SECRET
        if not secret or not constant_time_compare(request.headers.get("Authorization", ""), "Bearer " + secret):
            from rest_framework.exceptions import AuthenticationFailed
            raise AuthenticationFailed("无效的网关认证")
        pending = revoke_local_login_session(request.data.get("session_token", ""), request.data.get("free_session", ""))
        return Response({"logged_out": True, "gateway_cleanup_pending": pending})


class AccountLogout(APIView):
    authentication_classes = ()
    permission_classes = ()

    def post(self, request):
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        raw = request.COOKIES.get(AUTH_COOKIE_NAME, "")
        authorization = request.headers.get("Authorization", "").split()
        if len(authorization) == 2 and authorization[0].lower() == "token":
            raw = authorization[1]
        cleanup_pending = revoke_local_login_session(raw, request.COOKIES.get("free_session", ""))
        response = Response({"message": "退出成功", "gateway_cleanup_pending": cleanup_pending})
        response.delete_cookie("free_session", path="/", samesite="Strict")
        clear_auth_cookie(response)
        return response


class AccountRegister(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle, LoginAccountRateThrottle)
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

        from app.accounts.names import ensure_username_available
        ensure_username_available(data['username'])
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



class LoginStatusView(APIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = ()
    def post(self, request):
        from app.accounts.login_guard import attach_fingerprint, request_fingerprint, fingerprint, remaining, valid_api_session, FingerprintRequired
        # Existing sessions never depend on render collection or its cooldown.
        # Renew a supplied receipt opportunistically for a subsequent password login.
        if valid_api_session(request):
            fp = request_fingerprint(request)
            if not fp:
                try:
                    data = request.data
                    fp = fingerprint(data.get("fingerprint")) if isinstance(data, dict) else {}
                except APIException:
                    fp = {}
            return attach_fingerprint(Response({"remaining_seconds": 0}), fp)
        fp = request_fingerprint(request)
        if not fp:
            data = request.data
            fp = fingerprint(data.get("fingerprint")) if isinstance(data, dict) else {}
        if not fp:
            raise FingerprintRequired()
        seconds = remaining(fp)
        return attach_fingerprint(Response({"remaining_seconds": seconds}), fp)


class LoginGuardView(APIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = ()
    def post(self, request):
        from app.accounts.login_guard import remaining, api_session_identity, COOKIE
        from types import SimpleNamespace
        if not constant_time_compare(request.headers.get("X-Gateway-Secret", ""), settings.GATEWAY_ADMIN_SECRET):
            return Response({}, status=401)
        cookies = {AUTH_COOKIE_NAME: str(request.data.get("api_token", "")),
                   "free_session": str(request.data.get("free_session", "")), COOKIE: str(request.data.get("fingerprint_cookie", ""))}
        proxy = SimpleNamespace(COOKIES=cookies, headers={}, META={}, data={})
        identity = api_session_identity(proxy)
        authenticated = identity is not None
        from app.accounts.login_guard import request_fingerprint
        seconds = 0 if authenticated else remaining(request_fingerprint(proxy))
        return Response({"authenticated": authenticated, "remaining_seconds": seconds, "is_superuser": bool(identity and identity[0].is_superuser)})
