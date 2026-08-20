from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.exceptions import ValidationError

from app.settings import SHOW_GITHUB, TURNSTILE_ENABLED, TURNSTILE_SITE_KEY
from app.utils import req_gateway


class VersionConfig(APIView):

    def get(self, request):
        return Response({
            'show_github': SHOW_GITHUB,
            'turnstile_enabled': TURNSTILE_ENABLED,
            'turnstile_site_key': TURNSTILE_SITE_KEY if TURNSTILE_ENABLED else '',
        })


class AccessControlView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        res = req_gateway("get", "/api/blocked-paths")
        return Response(res)

    def post(self, request):
        paths = request.data.get("paths", request.data.get("hash_paths", []))
        res = req_gateway("post", "/api/blocked-paths", json={"paths": paths})
        return Response(res)


class PoliticalModerationConfigView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    @staticmethod
    def payload(request, force_enabled=None):
        enabled = request.data.get("enabled", False)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in ("1", "true", "yes", "on")
        if force_enabled is not None:
            enabled = force_enabled
        return {
            "enabled": bool(enabled),
            "protocol": request.data.get("protocol") or "openai_chat",
            "model": request.data.get("model") or "",
            "api_key": request.data.get("api_key") or "",
            "base_url": request.data.get("base_url") or "https://api.openai.com/v1",
            "mode": request.data.get("mode") or "relaxed",
            "custom_terms": request.data.get("custom_terms") or [],
            "limit_per_minute": request.data.get("limit_per_minute", 10),
            "limit_per_five_minutes": request.data.get("limit_per_five_minutes", 30),
            "limit_per_hour": request.data.get("limit_per_hour", 120),
        }

    def get(self, request):
        return Response(req_gateway("get", "/api/political-moderation-config"))

    def post(self, request):
        return Response(req_gateway(
            "post",
            "/api/political-moderation-config",
            json=self.payload(request),
        ))


class PoliticalModerationTestView(PoliticalModerationConfigView):
    def post(self, request):
        return Response(req_gateway(
            "post",
            "/api/political-moderation-config/test",
            json=self.payload(request, force_enabled=True),
        ))
