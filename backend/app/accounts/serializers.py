from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.accounts.models import Announcement, User, VisitLog
from app.chatgpt.models import ChatgptAccount
from app.settings import ADMIN_USERNAME


class ShowVisitLogModelSerializer(serializers.ModelSerializer):
    is_protected = serializers.SerializerMethodField()

    def get_is_protected(self, obj):
        return obj.username == ADMIN_USERNAME and obj.log_type == "login"

    class Meta:
        model = VisitLog
        fields = "__all__"


class ShowUserAccountModelSerializer(serializers.ModelSerializer):
    last_login = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    date_joined = serializers.DateTimeField(format="%Y-%m-%d %H:%M")
    use_count = serializers.SerializerMethodField()
    chatgpt_count = serializers.SerializerMethodField()
    conversation_count = serializers.SerializerMethodField()
    message_count = serializers.SerializerMethodField()
    model_message_counts = serializers.SerializerMethodField()

    def __init__(self, *args, use_count_dict=None, conversation_stats_dict=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_count_dict = use_count_dict or {}
        self.conversation_stats_dict = conversation_stats_dict or {}

    def get_chatgpt_count(self, obj):
        return ChatgptAccount.get_by_gptcar_list(obj.gptcar_list).count()

    def get_use_count(self, obj):
        return self.use_count_dict.get(obj.username, 0)

    def get_conversation_count(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("conversation_count", 0)

    def get_message_count(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("message_count", 0)

    def get_model_message_counts(self, obj):
        return self.conversation_stats_dict.get(obj.username, {}).get("model_message_counts", {})

    class Meta:
        model = User
        exclude = (
            "password", "is_superuser", "first_name", "last_name", "email", "is_staff", "groups", "user_permissions")
        # fields = "__all__"


class AddUserAccountSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    is_active = serializers.BooleanField()
    username = serializers.CharField(min_length=4)
    password = serializers.CharField(required=False)
    gptcar_list = serializers.JSONField(default=list)
    model_limit = serializers.JSONField(default=dict)
    remark = serializers.CharField(default="", allow_blank=True)
    isolated_session = serializers.BooleanField()
    expired_date = serializers.DateField(required=False, allow_null=True)
    daily_quota = serializers.IntegerField(required=False, min_value=0, default=0)
    monthly_quota = serializers.IntegerField(required=False, min_value=0, default=0)
    force_chat_mode = serializers.BooleanField(required=False)

    def validate_password(self, value):
        if not value:
            return value
        try:
            validate_password(
                value,
                User(username=str(self.initial_data.get("username") or "")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class BatchModelLimitSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(child=serializers.IntegerField())
    model_limit = serializers.JSONField()


class UserBindChatGPTSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(child=serializers.IntegerField())
    gptcar_id_list = serializers.ListField(child=serializers.IntegerField())


class BatchUserActionSerializer(serializers.Serializer):
    user_id_list = serializers.ListField(
        child=serializers.IntegerField(), min_length=1, max_length=200
    )
    action = serializers.ChoiceField(choices=["activate", "deactivate", "delete"])


class UserRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(min_length=4)
    password = serializers.CharField()
    chatgpt_token = serializers.CharField()

    def validate_password(self, value):
        try:
            validate_password(
                value,
                User(username=str(self.initial_data.get("username") or "")),
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_new_password(self, value):
        try:
            validate_password(value, self.context.get("user"))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ConversationTitlePrivacySerializer(serializers.Serializer):
    allow_admin_view_conversation_titles = serializers.BooleanField()


class AnnouncementSerializer(serializers.ModelSerializer):
    target_user_id = serializers.IntegerField(read_only=True, allow_null=True)
    target_username = serializers.CharField(source="target_user.username", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    status = serializers.SerializerMethodField()

    @staticmethod
    def get_status(obj):
        now = timezone.now()
        if not obj.is_active:
            return "disabled"
        if obj.start_at > now:
            return "scheduled"
        if obj.end_at is not None and obj.end_at <= now:
            return "history"
        return "current"

    class Meta:
        model = Announcement
        fields = (
            "id",
            "title",
            "content",
            "scope",
            "target_user_id",
            "target_username",
            "is_active",
            "start_at",
            "end_at",
            "display_timezone",
            "status",
            "created_by_username",
            "created_at",
            "updated_at",
        )


class AnnouncementWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=120)
    content = serializers.CharField(max_length=10000)
    scope = serializers.ChoiceField(
        choices=(Announcement.SCOPE_GLOBAL, Announcement.SCOPE_PERSONAL)
    )
    target_user_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    is_active = serializers.BooleanField(required=False, default=True)
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    end_at = serializers.DateTimeField(required=False, allow_null=True)
    display_timezone = serializers.CharField(required=False, default="Asia/Shanghai", max_length=64)

    def validate(self, attrs):
        display_timezone = attrs.get("display_timezone", "Asia/Shanghai").strip()
        try:
            ZoneInfo(display_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError({"display_timezone": "请选择有效的 IANA 时区"})
        attrs["display_timezone"] = display_timezone

        start_at = attrs.get("start_at")
        if start_at is None:
            start_at = self.instance.start_at if self.instance is not None else timezone.now()
            attrs["start_at"] = start_at
        end_at = attrs.get("end_at")
        if end_at is not None and end_at <= start_at:
            raise serializers.ValidationError({"end_at": "结束时间必须晚于开始时间"})

        target_user_id = attrs.pop("target_user_id", None)
        if attrs["scope"] == Announcement.SCOPE_GLOBAL:
            attrs["target_user"] = None
            return attrs

        target_user = User.objects.filter(id=target_user_id).first()
        if target_user is None:
            raise serializers.ValidationError({"target_user_id": "请选择有效的目标用户"})
        attrs["target_user"] = target_user
        return attrs

    def create(self, validated_data):
        return Announcement.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
