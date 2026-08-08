from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from app.accounts.models import User, VisitLog
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

    def __init__(self, *args, use_count_dict=dict, **kwargs):
        super().__init__(*args, **kwargs)
        self.use_count_dict = use_count_dict

    def get_chatgpt_count(self, obj):
        return ChatgptAccount.get_by_gptcar_list(obj.gptcar_list).count()

    def get_use_count(self, obj):
        return self.use_count_dict.get(obj.username, 0)

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
