from rest_framework import serializers

from app.chatgpt.models import ChatgptAccount, ChatgptCar
import jwt
from app.utils import clean_int_list
import time

class ShowGptCarSerializer(serializers.ModelSerializer):
    gpt_account_name_list = serializers.SerializerMethodField()

    def get_gpt_account_name_list(self, obj):
        gpt_account_list = clean_int_list(obj.gpt_account_list)
        resutls = ChatgptAccount.objects.filter(id__in=gpt_account_list).values_list("chatgpt_username")
        return [i[0] for i in resutls]

    class Meta:
        model = ChatgptCar
        fields = "__all__"

class AddChatgptCarModelSerializer(serializers.ModelSerializer):

    def validate_empty_values(self, data):
        if not self.instance:
            data["created_time"] = int(time.time())

        data["updated_time"] = int(time.time())
        return (False, data)

    class Meta:
        model = ChatgptCar
        fields = "__all__"

class DeleteChatgptCarSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField())


class ShowChatgptTokenSerializer(serializers.ModelSerializer):
    access_token_exp = serializers.SerializerMethodField()
    supported_login_modes = serializers.SerializerMethodField()
    has_refresh_token = serializers.SerializerMethodField()
    credential_source = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()
    automation = serializers.SerializerMethodField()
    usage = serializers.SerializerMethodField()

    def get_automation(self, obj):
        return bool(obj.web_identity_id)

    def get_usage(self, obj):
        from app.chatgpt.usage_monitor import public_usage
        return public_usage(obj, detailed=True)

    def get_credential_source(self, obj):
        return "automation" if obj.web_identity_id else "manual"

    def get_usage(self, obj):
        from app.chatgpt.usage_monitor import public_usage
        return public_usage(obj, detailed=True)

    def get_access_token_exp(self, obj):
        if not obj.access_token_valid:
            return None
        try:
            expiry = jwt.decode(obj.access_token, options={"verify_signature": False}).get("exp")
            return expiry if type(expiry) is int else None
        except Exception:
            return None

    def get_supported_login_modes(self, obj):
        modes = []
        if obj.access_token_valid:
            modes.append("api")
        if obj.session_token_valid:
            modes.append("web")
        return modes

    def get_has_refresh_token(self, obj):
        return bool(obj.refresh_token)

    class Meta:
        model = ChatgptAccount
        fields = (
            "id",
            "chatgpt_username",
            "auth_status",
            "plan_type",
            "access_token_valid",
            "session_token_valid",
            "proxy_node_id",
            "last_check_at",
            "last_error",
            "remark",
            "created_time",
            "updated_time",
            "access_token_exp",
            "login_count",
            "supported_login_modes",
            "has_refresh_token", "credential_source", "usage",
            "automation", "usage",
        )


class AddChatgptTokenSerializer(serializers.Serializer):
    account_id = serializers.IntegerField(required=False, min_value=1)
    auth_type = serializers.ChoiceField(choices=["cookie", "refresh_token"], default="cookie", required=False)
    chatgpt_token_list = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False)
    client_id = serializers.CharField(required=False, allow_blank=True)
    refresh_token = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        auth_type = attrs.get("auth_type") or "cookie"
        if auth_type == "refresh_token":
            if not (attrs.get("client_id") or "").strip():
                raise serializers.ValidationError({"client_id": "client_id 不能为空"})
            if not (attrs.get("refresh_token") or "").strip():
                raise serializers.ValidationError({"refresh_token": "refresh_token 不能为空"})
        elif not attrs.get("chatgpt_token_list"):
            raise serializers.ValidationError({"chatgpt_token_list": "Token 列表不能为空"})
        return attrs

class CheckChatgptTokenExpirySerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), required=False)

class RefreshChatgptTokenSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    force_web = serializers.BooleanField(default=False)


class ResetChatgptLoginCountSerializer(serializers.Serializer):
    id = serializers.IntegerField()

class DeleteChatgptAccountSerializer(serializers.Serializer):
    chatgpt_username = serializers.CharField()

class UpdateChatgptInfoSerializer(serializers.Serializer):
    chatgpt_username = serializers.CharField()
    remark = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    proxy_node_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class ChatGPTLoginSerializer(serializers.Serializer):
    chatgpt_id = serializers.IntegerField(required=False, allow_null=True)
    login_mode = serializers.ChoiceField(choices=["api", "web"], default="api", required=False)
