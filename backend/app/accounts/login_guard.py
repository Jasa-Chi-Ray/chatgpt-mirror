"""Persistent visitor login cooldown; authenticated sessions always bypass it."""
import hashlib
import math
import re
import time
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission

from app.accounts.models import LoginFailureState, LoginGuardMutex, VisitLog

COOKIE = "mirror_login_fingerprint"
SALT = "mirror.login.fingerprint.v1"
COOLDOWN_SECONDS = 120


def fingerprint(data):
    if not isinstance(data, dict):
        return {}
    out = {}
    for key in ("canvas", "webgl", "fonts", "layout"):
        value = data.get(key)
        if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
            out[key] = value
    shape = data.get("shape")
    if isinstance(shape, str) and re.fullmatch(r"[a-f0-9]{16}", shape):
        out["shape"] = shape
    return out if len(out) == 5 else {}


def anchor(fp):
    if not fp:
        return ""
    return salted_hmac(SALT + ".anchor", ":".join(fp[k] for k in ("webgl", "fonts", "layout"))).hexdigest()


def fingerprint_key(fp):
    """A private, IP-independent identity for per-renderer request throttles."""
    if not fp:
        return ""
    return salted_hmac(SALT + ".renderer", ":".join(fp[k] for k in
                       ("canvas", "webgl", "fonts", "layout", "shape"))).hexdigest()


def similar(left, right):
    if not left or not right or anchor(left) != anchor(right):
        return False
    return left["canvas"] == right["canvas"] or (int(left["shape"], 16) ^ int(right["shape"], 16)).bit_count() <= 1


def request_fingerprint(request):
    # Admission and counting use only the server-signed browser receipt. A login
    # payload cannot replace it or reset an existing rendering identity.
    try:
        return fingerprint(signing.loads(request.COOKIES.get(COOKIE, ""), salt=SALT, max_age=86400))
    except (signing.BadSignature, TypeError, ValueError):
        return {}


def attach_fingerprint(response, fp):
    if fp:
        response.set_cookie(COOKIE, signing.dumps(fp, salt=SALT, compress=True), max_age=86400,
                            secure=settings.SESSION_COOKIE_SECURE, httponly=True, samesite="Strict", path="/")
    return response


def valid_api_session(request):
    proof = hashlib.sha256(("login-cooldown-bypass:" + settings.GATEWAY_ADMIN_SECRET).encode()).hexdigest()
    if constant_time_compare(request.headers.get("X-Mirror-Cooldown-Bypass", ""), proof):
        return True
    from app.accounts.authentication import ExpiringCookieTokenAuthentication
    class ReadOnlyAuthentication(ExpiringCookieTokenAuthentication):
        @staticmethod
        def _enforce_csrf(_request):
            pass
    try:
        return ReadOnlyAuthentication().authenticate(request) is not None
    except APIException:
        return False


def remaining(fp):
    # IP is audit metadata only: shared NAT exits never join visitor bans.
    key = anchor(fp)
    if not key:
        return 0
    now = timezone.now()
    active = LoginFailureState.objects.filter(blocked_until__gt=now, fingerprint_anchor=key)
    until = None
    for row in active.only("fingerprint", "blocked_until").iterator():
        if similar(fp, row.fingerprint) and (until is None or row.blocked_until > until):
            until = row.blocked_until
    return max(0, math.ceil((until - now).total_seconds())) if until else 0


class LoginCooling(APIException):
    status_code = 401
    default_code = "login_cooling"
    def __init__(self, seconds):
        # The public response contains only a numeric remaining duration.
        self.detail = {"remaining_seconds": int(seconds)}


class FingerprintRequired(APIException):
    status_code = 401
    default_code = "fingerprint_required"
    default_detail = "浏览器渲染验证未完成，请允许 Canvas 渲染和 Cookie 后重新检测。"

    def __init__(self):
        self.detail = {"code": self.default_code, "message": self.default_detail}


def enforce_login(request):
    if valid_api_session(request):
        return
    fp = request_fingerprint(request)
    if not fp:
        raise FingerprintRequired()
    seconds = remaining(fp)
    if seconds:
        raise LoginCooling(seconds)


class LoginAdmissionPermission(BasePermission):
    """Run before throttles, password validation, ticket consumption or Turnstile."""
    def has_permission(self, request, view):
        enforce_login(request)
        return True


def account_digest(username):
    return salted_hmac(SALT + ".account", username.strip().casefold()).hexdigest()


def record_failure(request, username):
    from app.utils import get_client_ip
    ip, fp = get_client_ip(request), request_fingerprint(request)
    if not fp:
        if valid_api_session(request):
            return 0
        raise FingerprintRequired()
    account = account_digest(username)
    key = salted_hmac(SALT + ".visitor", account + ":" + fingerprint_key(fp)).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        # A database write serializes increments on SQLite as well as PostgreSQL.
        LoginGuardMutex.objects.filter(pk=1).update(touched_at=now)
        # This also finds existing records created before IP enforcement was removed.
        row = next((candidate for candidate in LoginFailureState.objects.filter(
            account_digest=account, fingerprint_anchor=anchor(fp)).order_by("-updated_at").iterator()
            if similar(fp, candidate.fingerprint)), None)
        if row is None:
            row = LoginFailureState(key=key, account_digest=account, ip=ip)
        row.ip = ip
        if row.blocked_until and row.blocked_until <= now:
            row.failures = 0
            row.blocked_until = None
        row.failures += 1
        row.fingerprint = fp
        row.fingerprint_anchor = anchor(fp)
        row.updated_at = now
        if row.failures >= 5:
            row.blocked_until = now + timedelta(seconds=COOLDOWN_SECONDS)
        row.save()
        if row.failures in (3, 5):
            VisitLog.objects.create(username=username[:150], log_type="login-failed" if row.failures == 3 else "login-cooldown",
                created_at=int(time.time()), ip=ip, user_agent=request.headers.get("User-Agent", "")[:512],
                failure_count=row.failures, cooldown_seconds=COOLDOWN_SECONDS if row.failures == 5 else 0)
        return COOLDOWN_SECONDS if row.failures >= 5 else 0


def reset_failures(request, username):
    fp = request_fingerprint(request)
    query = LoginFailureState.objects.filter(account_digest=account_digest(username), blocked_until__isnull=True)
    if anchor(fp):
        for row in query.filter(fingerprint_anchor=anchor(fp)):
            if similar(fp, row.fingerprint):
                row.delete()


class LoginGuardMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    def __call__(self, request):
        # Internal guard calls are authenticated by the shared service secret.
        if (request.path == "/0x/user/login-guard" or
                (request.path == "/0x/user/version-cfg" and request.headers.get("X-Mirror-Healthcheck") == "1")) and constant_time_compare(
                request.headers.get("X-Gateway-Secret", ""), settings.GATEWAY_ADMIN_SECRET):
            return self.get_response(request)
        if request.path == "/0x/user/login-status" or valid_api_session(request):
            return self.get_response(request)
        seconds = remaining(request_fingerprint(request))
        if seconds:
            # Login submissions may return seconds; all other endpoints return 401.
            return JsonResponse({"remaining_seconds": seconds} if request.path in
                ("/0x/user/login", "/0x/user/login-free", "/0x/user/register", "/0x/user/login-confirm") else {}, status=401)
        return self.get_response(request)
