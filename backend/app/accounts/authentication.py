from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError

from app.security import ConfigurableCsrfViewMiddleware


AUTH_COOKIE_NAME = "mirror_api_session"


class _CsrfCheck(ConfigurableCsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


class ExpiringCookieTokenAuthentication(TokenAuthentication):
    """Authenticate API clients by header or by a scoped HttpOnly cookie."""

    def authenticate(self, request):
        header = get_authorization_header(request)
        cookie_token = request.COOKIES.get(AUTH_COOKIE_NAME, "").strip()
        if header:
            result = super().authenticate(request)
        elif cookie_token:
            result = self.authenticate_credentials(cookie_token)
            self._enforce_csrf(request)
        else:
            return None

        if result is None:
            return None
        user, token = result
        expires_at = token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS)
        expired_account = user.expired_date and user.expired_date <= timezone.localdate()
        if timezone.now() >= expires_at or not user.is_active or expired_account:
            type(token).objects.filter(user=user).delete()
            raise AuthenticationFailed("登录已过期，请重新登录")
        if user.username == settings.FREE_ACCOUNT_USERNAME:
            from app.utils import get_request_subject
            request.user = user
            try:
                get_request_subject(request)
            except ValidationError:
                raise AuthenticationFailed("免费访客会话已失效，请重新进入")
        return user, token

    @staticmethod
    def _enforce_csrf(request):
        check = _CsrfCheck(lambda _request: None)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise PermissionDenied(f"CSRF 验证失败: {reason}")


def set_auth_cookie(response, token):
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token.key,
        max_age=settings.API_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="Strict",
        path="/0x/",
    )


def clear_auth_cookie(response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/0x/", samesite="Strict")
