from django.contrib.auth.models import AbstractUser, AbstractBaseUser
from django.db import models
from django.db.models import Q
from django.utils import timezone
from app.chatgpt.models import ChatgptAccount


class User(AbstractUser):
    model_limit = models.JSONField(default=list, verbose_name="备注")
    remark = models.TextField(blank=True, verbose_name="备注")
    isolated_session = models.BooleanField(default=True, verbose_name="独立回话")
    gptcar_list = models.JSONField(default=list)
    expired_date = models.DateField(blank=True, null=True, verbose_name="过期日期")
    daily_quota = models.PositiveIntegerField(default=0, verbose_name="每日配额")
    monthly_quota = models.PositiveIntegerField(default=0, verbose_name="每月配额")
    force_chat_mode = models.BooleanField(default=True, verbose_name="自动退出 Work 模式")
    allow_admin_view_conversation_titles = models.BooleanField(
        default=False,
        verbose_name="允许管理员查看对话标题",
    )


class Announcement(models.Model):
    SCOPE_GLOBAL = "global"
    SCOPE_PERSONAL = "personal"
    SCOPE_CHOICES = (
        (SCOPE_GLOBAL, "全局公告"),
        (SCOPE_PERSONAL, "个人公告"),
    )

    title = models.CharField(max_length=120, verbose_name="标题")
    content = models.TextField(verbose_name="内容")
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, verbose_name="范围")
    target_user = models.ForeignKey(
        User,
        related_name="targeted_announcements",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        verbose_name="目标用户",
    )
    is_active = models.BooleanField(default=True, verbose_name="启用")
    start_at = models.DateTimeField(default=timezone.now, verbose_name="开始时间")
    end_at = models.DateTimeField(null=True, blank=True, verbose_name="结束时间")
    display_timezone = models.CharField(
        max_length=64,
        default="Asia/Shanghai",
        verbose_name="显示时区",
    )
    created_by = models.ForeignKey(
        User,
        related_name="created_announcements",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="发布人",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=(
                    Q(scope="global", target_user__isnull=True)
                    | Q(scope="personal", target_user__isnull=False)
                ),
                name="announcement_scope_matches_target",
            ),
        )
        indexes = (
            models.Index(fields=("scope", "is_active"), name="announce_scope_active_idx"),
            models.Index(fields=("target_user", "is_active"), name="announce_user_active_idx"),
        )


class VisitLog(models.Model):
    # user = models.ForeignKey(User, db_constraint=False, on_delete=models.SET_NULL, null=True)
    username = models.CharField(max_length=150, verbose_name="用户名")
    chatgpt_username = models.CharField(max_length=150, null=True, verbose_name="chatgpt")
    log_type = models.CharField(max_length=20, verbose_name="登录类型")
    created_at = models.IntegerField(verbose_name="登录时间")
    ip = models.GenericIPAddressField(verbose_name="登录IP")
    user_agent = models.TextField(verbose_name="User-Agent")

    @classmethod
    def save_data(cls, data):
        obj = cls.objects.create(**data)
        return obj
