from copy import copy

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from app.chatgpt.health_mail import MailDeliveryError, send_notification, test_imap
from app.chatgpt.models import AccountHealthSettings, AccountHealthState
from app.permissions import IsSuperUser


def recipient_changed(new, old):
    return new.strip().casefold() != old.strip().casefold()


class HealthSettingsSerializer(serializers.ModelSerializer):
    smtp_password = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=4096, trim_whitespace=False)
    imap_password = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=4096, trim_whitespace=False)
    smtp_configured = serializers.SerializerMethodField()
    imap_configured = serializers.SerializerMethodField()
    interval_minutes = serializers.IntegerField(min_value=2, max_value=10080)
    smtp_port = serializers.IntegerField(min_value=1, max_value=65535)
    imap_port = serializers.IntegerField(min_value=1, max_value=65535)
    smtp_security = serializers.ChoiceField(choices=["ssl", "starttls"])
    imap_security = serializers.ChoiceField(choices=["ssl", "starttls"])
    revision = serializers.IntegerField(min_value=0)
    test_on_recipient_change = serializers.BooleanField(default=False, write_only=True)

    class Meta:
        model = AccountHealthSettings
        fields = ("enabled", "interval_minutes", "recipient", "smtp_host", "smtp_port",
                  "smtp_security", "smtp_username", "smtp_password", "smtp_configured",
                  "imap_host", "imap_port", "imap_security", "imap_username", "imap_password",
                  "imap_configured", "revision", "test_on_recipient_change", "last_sent_at", "last_mail_error")
        read_only_fields = ("last_sent_at", "last_mail_error")

    def get_smtp_configured(self, obj):
        return bool(obj.smtp_password)

    def get_imap_configured(self, obj):
        return bool(obj.imap_password)

    def validate(self, attrs):
        candidate = copy(self.instance)
        for key, value in attrs.items():
            if key.endswith("_password") and not value:
                continue
            setattr(candidate, key, value)
        for protocol in ("smtp", "imap"):
            host = getattr(candidate, protocol + "_host")
            if host and (len(host) > 253 or any(c in host for c in "/\\:@?# \r\n\t")):
                raise ValidationError({protocol + "_host": "只填写服务器域名或 IPv4 地址，不含协议、路径或端口"})
            # Never forward a retained credential to a newly selected server/identity.
            changed = any(getattr(candidate, protocol + suffix) != getattr(self.instance, protocol + suffix)
                          for suffix in ("_host", "_port", "_security", "_username"))
            if changed and getattr(self.instance, protocol + "_password") and not attrs.get(protocol + "_password"):
                raise ValidationError({protocol + "_password": "更换连接配置时请重新填写授权码"})
            if attrs.get(protocol + "_password", "").startswith("enc:v1:"):
                raise ValidationError({protocol + "_password": "请填写原始授权码"})
        if candidate.enabled or (attrs.get("test_on_recipient_change") and recipient_changed(candidate.recipient, self.instance.recipient)):
            if not all((candidate.recipient, candidate.smtp_host, candidate.smtp_username, candidate.smtp_password)):
                raise ValidationError("请先填写收件邮箱及完整 SMTP 配置")
        if candidate.imap_host and not all((candidate.imap_username, candidate.imap_password)):
            raise ValidationError("填写 IMAP 服务器后需同时填写用户名和授权码")
        return attrs


class AccountHealthSettingsView(APIView):
    permission_classes = (IsAuthenticated, IsSuperUser)

    def get(self, request):
        config, _ = AccountHealthSettings.objects.get_or_create(pk=1)
        return Response(HealthSettingsSerializer(config).data)

    def put(self, request):
        config, _ = AccountHealthSettings.objects.get_or_create(pk=1)
        serializer = HealthSettingsSerializer(config, data=request.data)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        revision = values.pop("revision")
        if revision != config.revision:
            raise ValidationError("配置已被更改，请关闭后重新打开")
        should_test = values.pop("test_on_recipient_change", False) and recipient_changed(values.get("recipient", config.recipient), config.recipient)
        values = {key: value for key, value in values.items() if not (key.endswith("_password") and not value)}
        candidate = copy(config)
        for key, value in values.items():
            setattr(candidate, key, value)
        if should_test:
            try:
                send_notification(candidate, "上游账号健康通知 · test", "这是一封 test 邮件，用于确认新收件邮箱可以收到账号健康通知。")
            except MailDeliveryError as exc:
                raise ValidationError(str(exc)) from None
        with transaction.atomic():
            if not AccountHealthSettings.objects.filter(pk=1, revision=revision).update(**values, revision=revision + 1):
                raise ValidationError("配置已被更改，请重新打开后保存")
            state_changes = dict(next_check_at=timezone.now(), first_failure_at=None, lease_token="", lease_until=None)
            if recipient_changed(candidate.recipient, config.recipient) or (candidate.enabled and not config.enabled):
                state_changes["notified"] = False
            AccountHealthState.objects.update(**state_changes)
        config.refresh_from_db()
        return Response({"message": "设置已保存；测试邮件已提交 SMTP" if should_test else "设置已保存", **HealthSettingsSerializer(config).data})

    def post(self, request):
        config, _ = AccountHealthSettings.objects.get_or_create(pk=1)
        action = request.data.get("action")
        try:
            if action == "test_imap":
                if not all((config.imap_host, config.imap_username, config.imap_password)):
                    raise ValidationError("请先保存完整的 IMAP 配置")
                test_imap(config)
                return Response({"message": "IMAP 连接及认证成功"})
            if action != "test_mail":
                raise ValidationError("未知操作")
            if not all((config.recipient, config.smtp_host, config.smtp_username, config.smtp_password)):
                raise ValidationError("请先保存完整的 SMTP 配置和收件邮箱")
            send_notification(config, "上游账号健康通知 · test", "这是一封 test 邮件，邮件通知服务连接正常。")
            AccountHealthSettings.objects.filter(pk=1, revision=config.revision).update(last_sent_at=timezone.now(), last_mail_error="")
        except MailDeliveryError as exc:
            raise ValidationError(str(exc)) from None
        return Response({"message": "测试邮件已提交 SMTP，请检查收件箱"})
