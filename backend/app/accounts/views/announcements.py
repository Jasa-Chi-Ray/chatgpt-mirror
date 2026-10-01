from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import Announcement, User
from app.accounts.serializers import AnnouncementSerializer, AnnouncementWriteSerializer
from app.utils import req_gateway


def active_login_block_for(user, now=None):
    now = now or timezone.now()
    return Announcement.objects.filter(
        is_active=True,
        block_chatgpt_login=True,
        start_at__lte=now,
    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now)).filter(
        Q(scope=Announcement.SCOPE_GLOBAL)
        | Q(scope=Announcement.SCOPE_PERSONAL, target_user=user)
    ).exists()


def sync_chatgpt_login_blocks():
    now = timezone.now()
    announcements = Announcement.objects.filter(
        is_active=True, block_chatgpt_login=True,
    ).filter(Q(end_at__isnull=True) | Q(end_at__gt=now)).select_related("target_user")
    rules = [{
        "id": item.id,
        "scope": item.scope,
        "target_user": item.target_user.username if item.target_user else None,
        "start_at": int(item.start_at.timestamp()),
        "end_at": int(item.end_at.timestamp()) if item.end_at else None,
    } for item in announcements]
    result = req_gateway("post", "/api/chatgpt-login-blocks", json={"rules": rules})
    if result.get("synced") is not True:
        raise ValidationError({"message": "网关未确认登录限制，请重试"})


@method_decorator(never_cache, name="dispatch")
class AnnouncementAdminView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        announcements = Announcement.objects.select_related("target_user", "created_by").all()
        users = User.objects.filter(is_active=True, is_superuser=False).order_by("username").values(
            "id", "username"
        )
        return Response({
            "results": AnnouncementSerializer(announcements, many=True).data,
            "users": list(users),
        })

    def post(self, request):
        serializer = AnnouncementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            announcement = serializer.save(created_by=request.user)
            if announcement.block_chatgpt_login:
                sync_chatgpt_login_blocks()
        return Response(AnnouncementSerializer(announcement).data, status=201)

    def put(self, request):
        announcement = self._get_announcement(request.data.get("id"))
        serializer = AnnouncementWriteSerializer(announcement, data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            was_blocking = announcement.block_chatgpt_login
            announcement = serializer.save()
            if was_blocking or announcement.block_chatgpt_login:
                sync_chatgpt_login_blocks()
        return Response(AnnouncementSerializer(announcement).data)

    def delete(self, request):
        announcement = self._get_announcement(request.data.get("id"))
        with transaction.atomic():
            was_blocking = announcement.block_chatgpt_login
            announcement.delete()
            if was_blocking:
                sync_chatgpt_login_blocks()
        return Response({"message": "公告已删除"})

    @staticmethod
    def _get_announcement(announcement_id):
        if not announcement_id:
            raise ValidationError({"id": "公告 ID 不能为空"})
        announcement = Announcement.objects.filter(id=announcement_id).first()
        if announcement is None:
            raise ValidationError({"id": "公告不存在"})
        return announcement


@method_decorator(never_cache, name="dispatch")
class CurrentAnnouncementView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        now = timezone.now()
        queryset = Announcement.objects.select_related(
            "target_user", "created_by"
        )
        applicable = queryset.filter(
            Q(scope=Announcement.SCOPE_GLOBAL)
            | Q(scope=Announcement.SCOPE_PERSONAL, target_user=request.user)
        )
        current = applicable.filter(is_active=True, start_at__lte=now).filter(
            Q(end_at__isnull=True) | Q(end_at__gt=now)
        )
        global_announcements = current.filter(scope=Announcement.SCOPE_GLOBAL)
        personal_announcements = current.filter(
            scope=Announcement.SCOPE_PERSONAL,
            target_user=request.user,
        )
        history = applicable.filter(start_at__lte=now, end_at__lte=now)
        return Response({
            "global": AnnouncementSerializer(global_announcements, many=True).data,
            "personal": AnnouncementSerializer(personal_announcements, many=True).data,
            "history": AnnouncementSerializer(history, many=True).data,
        })
