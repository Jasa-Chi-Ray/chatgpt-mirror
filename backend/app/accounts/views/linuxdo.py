"""Linux DO authorization-code login. Provider tokens never leave this module."""
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.authtoken.serializers import AuthTokenSerializer
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.authentication import ExpiringCookieTokenAuthentication
from app.accounts.login_guard import (LoginAdmissionPermission, LoginCooling, remaining,
    request_fingerprint, record_failure, reset_failures, valid_api_session,
    FingerprintRequired)
from app.accounts.models import User, OAuthFlow, OAuthIdentity, LoginGuardMutex
from app.accounts.session_authority import digest
from app.accounts.views.login import (pending_login, verify_turnstile,
    LoginFingerprintRateThrottle, PasswordAttemptRateThrottle)
from app.utils import save_visit_log

AUTHORIZE_URL = 'https://connect.linux.do/oauth2/authorize'
TOKEN_URL = 'https://connect.linux.do/oauth2/token'
USER_URL = 'https://connect.linux.do/api/user'
FLOW_TTL = timedelta(minutes=10)
ERRORS = {
    'cancelled': 'Linux DO 授权已取消',
    'expired': 'Linux DO 登录已过期，请重新授权',
    'failed': 'Linux DO 登录暂时不可用，请重试',
    'unavailable': '此 Linux DO 账号暂时无法登录本站',
}


def enabled():
    if not settings.LINUXDO_OAUTH_ENABLED:
        raise ValidationError({'message': 'Linux DO 登录未启用'})


def browser_matches(request, flow):
    # Django's CSRF cookie is SameSite=Lax and is already forwarded by Gateway.
    # The Strict authentication/fingerprint cookies need not cross the provider redirect.
    value = request.META.get('CSRF_COOKIE', '')
    return bool(value and constant_time_compare(flow.browser_digest, digest(value)))


def current_login(request):
    result = ExpiringCookieTokenAuthentication().authenticate(request)
    if not result:
        raise PermissionDenied('请先登录镜像账号')
    user, token = result
    if user.username == settings.FREE_ACCOUNT_USERNAME:
        raise PermissionDenied('免费体验账号不能绑定第三方登录')
    return user, token


def eligible(profile):
    if (profile.get('active') is not True or profile.get('silenced') not in (False, None)
            or type(profile.get('trust_level')) is not int
            or not settings.LINUXDO_MIN_TRUST_LEVEL <= profile['trust_level'] <= 4):
        raise ValueError('provider account unavailable')
    subject = str(profile.get('id', ''))
    username = profile.get('username')
    if (not re.fullmatch(r'[1-9][0-9]{0,19}', subject) or not isinstance(username, str)
            or not username or len(username) > 150 or any(ord(c) < 32 for c in username)):
        raise ValueError('provider profile invalid')
    return {'id': subject, 'username': username}


def provider_profile(code):
    # Fixed HTTPS endpoints, no redirects, bounded response, and no response logging.
    with requests.post(TOKEN_URL, data={
        'client_id': settings.LINUXDO_CLIENT_ID,
        'client_secret': settings.LINUXDO_CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code,
        'redirect_uri': settings.LINUXDO_REDIRECT_URI,
    }, headers={'Accept': 'application/json'}, timeout=(5, 10), allow_redirects=False) as response:
        if response.status_code != 200 or len(response.content) > 65536:
            raise ValueError('provider token response invalid')
        token = response.json().get('access_token')
        if not isinstance(token, str) or not token or len(token) > 16384 or any(c in token for c in '\r\n'):
            raise ValueError('provider token missing')
    with requests.get(USER_URL, headers={'Authorization': 'Bearer ' + token,
            'Accept': 'application/json'}, timeout=(5, 10), allow_redirects=False) as response:
        if response.status_code != 200 or len(response.content) > 65536:
            raise ValueError('provider profile response invalid')
        profile = response.json()
    if not isinstance(profile, dict):
        raise ValueError('provider profile invalid')
    return eligible(profile)


def redirect(flow=None, **params):
    page = '/account/profile' if flow and flow.intent == 'link' else '/login'
    response = HttpResponseRedirect('/admin/#' + page + '?' + urlencode(params))
    response['Referrer-Policy'] = 'no-referrer'
    response['Cache-Control'] = 'private, no-store'
    return response


def ready_flow(request):
    raw = str(request.data.get('result') or '')
    if not re.fullmatch('[a-f0-9]{64}', raw):
        raise ValidationError({'message': ERRORS['expired']})
    flow = OAuthFlow.objects.select_for_update().filter(
        result_digest=digest(raw), stage='ready', expires_at__gt=timezone.now()).first()
    if not flow or not browser_matches(request, flow):
        raise ValidationError({'message': ERRORS['expired']})
    seconds = 0 if valid_api_session(request) else remaining(flow.fingerprint)
    if seconds:
        raise LoginCooling(seconds)
    return flow


def check_user(user):
    if not user.is_active or (user.expired_date and user.expired_date <= timezone.localdate()):
        raise ValidationError({'message': '账号已停用或已过期，请联系管理员'})
    if user.username == settings.FREE_ACCOUNT_USERNAME:
        raise ValidationError({'message': '免费体验账号不能绑定第三方登录'})


def link_identity(user, profile):
    check_user(user)
    identity = OAuthIdentity.objects.filter(provider='linuxdo', subject=profile['id']).first()
    other = OAuthIdentity.objects.filter(provider='linuxdo', user=user).first()
    if (identity and identity.user_id != user.pk) or (other and other.subject != profile['id']):
        raise ValidationError({'message': '该账号已存在其他绑定，请先解除原绑定'})
    identity, _ = OAuthIdentity.objects.update_or_create(provider='linuxdo', subject=profile['id'],
        defaults={'user': user, 'username': profile['username']})
    return identity


class LinuxDOStartView(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle,)

    def post(self, request):
        enabled()
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        intent = request.data.get('intent', 'login')
        if intent not in ('login', 'link'):
            raise ValidationError({'message': '不支持的登录操作'})
        user = token = None
        if intent == 'link':
            user, token = current_login(request)
        else:
            verify_turnstile(request, 'login')
        state = secrets.token_hex(32)
        OAuthFlow.objects.filter(expires_at__lte=timezone.now()).delete()
        OAuthFlow.objects.create(state_digest=digest(state), intent=intent,
            admitted_session=valid_api_session(request),
            browser_digest=digest(request.META['CSRF_COOKIE']), user=user,
            session_digest=digest(token.key) if token else '', fingerprint=request_fingerprint(request),
            expires_at=timezone.now() + FLOW_TTL)
        return Response({'authorize_url': AUTHORIZE_URL + '?' + urlencode({
            'client_id': settings.LINUXDO_CLIENT_ID, 'redirect_uri': settings.LINUXDO_REDIRECT_URI,
            'response_type': 'code', 'scope': 'user', 'state': state})})


class LinuxDOCallbackView(APIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = ()

    def get(self, request):
        enabled()
        state = request.query_params.get('state', '')
        if not re.fullmatch('[a-f0-9]{64}', state) or len(request.query_params.getlist('state')) != 1:
            return redirect(linuxdo_error='expired')
        flow = OAuthFlow.objects.filter(state_digest=digest(state), stage='started',
            expires_at__gt=timezone.now()).first()
        if not flow or not browser_matches(request, flow):
            return redirect(linuxdo_error='expired')
        if flow.intent == 'login' and not flow.admitted_session and remaining(flow.fingerprint):
            return redirect(flow, linuxdo_error='unavailable')
        # Claim before contacting the provider. A callback cannot be replayed.
        if not OAuthFlow.objects.filter(pk=flow.pk, stage='started').update(stage='processing'):
            return redirect(linuxdo_error='expired')
        if request.query_params.get('error'):
            flow.delete()
            return redirect(flow, linuxdo_error='cancelled')
        code = request.query_params.get('code', '')
        try:
            if not code or len(code) > 4096 or len(request.query_params.getlist('code')) != 1:
                raise ValueError('invalid code')
            profile = provider_profile(code)
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            flow.delete()
            return redirect(flow, linuxdo_error='failed')
        raw = secrets.token_hex(32)
        OAuthFlow.objects.filter(pk=flow.pk, stage='processing').update(
            stage='ready', profile=profile, result_digest=digest(raw))
        return redirect(flow, linuxdo_result=raw)


class LinuxDOCompleteView(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle,)

    def post(self, request):
        enabled()
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        try:
            with transaction.atomic():
                LoginGuardMutex.objects.filter(pk=1).update(touched_at=timezone.now())
                flow = ready_flow(request)
                if flow.intent == 'link':
                    user, token = current_login(request)
                    if user.pk != flow.user_id or not constant_time_compare(flow.session_digest, digest(token.key)):
                        raise PermissionDenied('登录状态已改变，请重新发起绑定')
                    link_identity(user, flow.profile)
                    flow.delete()
                    request.user = user
                    save_visit_log(request, 'oauth-link')
                    return Response({'linked': True})
                identity = OAuthIdentity.objects.select_related('user').filter(
                    provider='linuxdo', subject=flow.profile['id']).first()
                if identity:
                    user = identity.user
                elif settings.ALLOW_REGISTER:
                    base = 'linuxdo_' + flow.profile['id']
                    username = base
                    while (username in (settings.ADMIN_USERNAME, settings.FREE_ACCOUNT_USERNAME)
                            or User.objects.filter(username=username).exists()):
                        username = base + '_' + secrets.token_hex(4)
                    from app.accounts.names import ensure_username_available
                    ensure_username_available(username)
                    user = User(username=username)
                    user.set_unusable_password()
                    user.save()
                else:
                    return Response({'requires_binding': True, 'linuxdo_username': flow.profile['username']})
                check_user(user)
                identity = link_identity(user, flow.profile)
                flow.delete()
                reset_failures(request, user.username)
                return pending_login(request, user, timezone.now() + timedelta(seconds=60),
                    oauth_identity=identity)
        except IntegrityError:
            raise ValidationError({'message': '绑定状态已改变，请重新授权'}) from None


class LinuxDOBindLoginView(APIView):
    authentication_classes = ()
    permission_classes = (LoginAdmissionPermission,)
    throttle_classes = (LoginFingerprintRateThrottle, PasswordAttemptRateThrottle)

    def post(self, request):
        enabled()
        ExpiringCookieTokenAuthentication._enforce_csrf(request)
        fp = request_fingerprint(request)
        if not fp:
            raise FingerprintRequired()
        seconds = remaining(fp)
        if seconds:
            raise LoginCooling(seconds)
        # Reject missing/expired/cross-browser results before testing any password.
        with transaction.atomic():
            flow = ready_flow(request)
            if flow.intent != 'login':
                raise ValidationError({'message': '请在账户中心完成绑定'})
        expires_at = verify_turnstile(request, 'login')
        serializer = AuthTokenSerializer(data=request.data, context={'request': request})
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            username = str(request.data.get('username') or '').strip()
            password = str(request.data.get('password') or '')
            account = User.objects.filter(username=username).first()
            if username and password and (account is None or not account.check_password(password)):
                seconds = record_failure(request, username)
                if seconds:
                    raise LoginCooling(seconds)
            raise
        user = serializer.validated_data['user']
        try:
            with transaction.atomic():
                LoginGuardMutex.objects.filter(pk=1).update(touched_at=timezone.now())
                flow = ready_flow(request)
                if flow.intent != 'login':
                    raise ValidationError({'message': '请在账户中心完成绑定'})
                identity = link_identity(user, flow.profile)
                flow.delete()
                response = pending_login(request, user, expires_at, oauth_identity=identity)
        except IntegrityError:
            raise ValidationError({'message': '绑定状态已改变，请重新授权'}) from None
        reset_failures(request, user.username)
        return response


class LinuxDOConnectionView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        identity = OAuthIdentity.objects.filter(provider='linuxdo', user=request.user).first()
        return Response({'enabled': settings.LINUXDO_OAUTH_ENABLED, 'linked': bool(identity),
            'username': identity.username if identity else '',
            'can_unlink': bool(identity and request.user.has_usable_password())})

    def delete(self, request):
        if request.user.username == settings.FREE_ACCOUNT_USERNAME or not request.user.has_usable_password():
            raise ValidationError({'message': '请先由管理员设置本地密码，再解除绑定'})
        with transaction.atomic():
            LoginGuardMutex.objects.filter(pk=1).update(touched_at=timezone.now())
            OAuthIdentity.objects.filter(provider='linuxdo', user=request.user).delete()
        save_visit_log(request, 'oauth-unlink')
        return Response({'linked': False})
