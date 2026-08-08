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
