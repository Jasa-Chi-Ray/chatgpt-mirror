import hashlib
import json
from datetime import timedelta, datetime, time

from django.conf import settings
from django.core import signing
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import VisitorSession

AUTHORIZATION_SALT = "mirror.gateway-authorization.v1"


def digest(value):
    return hashlib.sha256(str(value).encode()).hexdigest()


def policy_digest(user):
    return digest(json.dumps({
        "pools": user.gptcar_list, "models": user.model_limit,
        "isolation": user.isolated_session, "force_chat": user.force_chat_mode,
        "mcp_isolation": user.mcp_isolation, "skills_isolation": user.skills_isolation,
        "capability_policy_initialized": user.capability_policy_initialized,
        "mcp_allowlist": user.mcp_allowlist, "skills_allowlist": user.skills_allowlist,
        "daily_quota": user.daily_quota, "monthly_quota": user.monthly_quota,
        "staff": user.is_staff, "superuser": user.is_superuser,
    }, sort_keys=True, separators=(",", ":")))


def capability_aliases(user, field):
    aliases = []
    for item in getattr(user, field, None) or []:
        if not isinstance(item, dict):
            continue
        for value in [item.get("id"), *(item.get("aliases") or [])]:
            value = str(value or "").strip()
            if value and value not in aliases:
                aliases.append(value)
    return aliases


def authorization_version(user, token):
    return digest(f"{user.pk}:{user.authorization_version}:{digest(token)}")


def gateway_authorization(request):
    from app.utils import get_request_subject

    return signing.dumps({
        "user_id": request.user.pk,
        "subject": get_request_subject(request),
        "token_digest": digest(request.auth),
        "policy_digest": policy_digest(request.user),
        "version": authorization_version(request.user, request.auth),
    }, salt=AUTHORIZATION_SALT)


def authorization_details(value, subject):
    try:
        payload = signing.loads(value, salt=AUTHORIZATION_SALT, max_age=settings.API_TOKEN_TTL_SECONDS)
        token = Token.objects.select_related("user").get(user_id=payload["user_id"])
        user = token.user
        if (not user.is_active or
                (user.expired_date and user.expired_date <= timezone.localdate()) or
                token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS) <= timezone.now() or
                not constant_time_compare(payload["token_digest"], digest(token.key)) or
                not constant_time_compare(payload["policy_digest"], policy_digest(user)) or
                not constant_time_compare(payload.get("version", ""), authorization_version(user, token.key)) or
                payload["subject"] != subject):
            return None
        expiry = min(timezone.now() + timedelta(hours=1), token.created + timedelta(seconds=settings.API_TOKEN_TTL_SECONDS))
        if user.expired_date:
            expiry = min(expiry, timezone.make_aware(datetime.combine(user.expired_date, time.min)))
        if user.username == settings.FREE_ACCOUNT_USERNAME:
            prefix = user.username + ":"
            if not subject.startswith(prefix):
                return None
            visitor = VisitorSession.objects.filter(sid=subject[len(prefix):], user=user,
                                                     expires_at__gt=timezone.now()).first()
            if not visitor:
                return None
            expiry = min(expiry, visitor.expires_at)
        elif subject != user.username:
            return None
        return {"active": True, "version": payload["version"], "expires_at": int(expiry.timestamp())}
    except (signing.BadSignature, Token.DoesNotExist, KeyError, TypeError, ValueError):
        return None


def authorization_is_active(value, subject):
    return authorization_details(value, subject) is not None


class GatewayAuthorizationView(APIView):
    authentication_classes = ()
    permission_classes = ()
    throttle_classes = ()

    def post(self, request):
        secret = settings.GATEWAY_ADMIN_SECRET
        if not secret or not constant_time_compare(
            request.headers.get("Authorization", ""), "Bearer " + secret,
        ):
            raise AuthenticationFailed("无效的网关认证")
        details = authorization_details(
            request.data.get("authorization", ""), request.data.get("subject", ""),
        )
        if not details:
            raise AuthenticationFailed("登录已失效，请重新登录")
        return Response(details)
