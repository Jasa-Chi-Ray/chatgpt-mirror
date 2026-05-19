from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.exceptions import ValidationError

from app.settings import SHOW_GITHUB
from app.utils import req_gateway


class VersionConfig(APIView):

    def get(self, request):
        return Response({'show_github': SHOW_GITHUB})


class AccessControlView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        res = req_gateway("get", "/api/blocked-paths")
        return Response(res)

    def post(self, request):
        hash_paths = request.data.get("hash_paths", [])
        res = req_gateway("post", "/api/blocked-paths", json={"hash_paths": hash_paths})
        return Response(res)
