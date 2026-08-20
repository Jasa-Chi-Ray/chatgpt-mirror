from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.db.models import Q
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import Announcement, User
from app.accounts.serializers import AnnouncementSerializer, AnnouncementWriteSerializer


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
        announcement = serializer.save(created_by=request.user)
        return Response(AnnouncementSerializer(announcement).data, status=201)

    def put(self, request):
        announcement = self._get_announcement(request.data.get("id"))
        serializer = AnnouncementWriteSerializer(announcement, data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        return Response(AnnouncementSerializer(announcement).data)

    def delete(self, request):
        announcement = self._get_announcement(request.data.get("id"))
        announcement.delete()
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
        if request.user.is_staff or request.user.is_superuser:
            return Response({"global": [], "personal": [], "history": []})

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
