from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_user_force_chat_mode")]

    operations = [
        migrations.CreateModel(
            name="Announcement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=120, verbose_name="标题")),
                ("content", models.TextField(verbose_name="内容")),
                (
                    "scope",
                    models.CharField(
                        choices=(("global", "全局公告"), ("personal", "个人公告")),
                        max_length=16,
                        verbose_name="范围",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_announcements",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="发布人",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="targeted_announcements",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="目标用户",
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at", "-id"),
                "indexes": (
                    models.Index(fields=["scope", "is_active"], name="announce_scope_active_idx"),
                    models.Index(fields=["target_user", "is_active"], name="announce_user_active_idx"),
                ),
                "constraints": (
                    models.CheckConstraint(
                        condition=(
                            models.Q(("scope", "global"), ("target_user__isnull", True))
                            | models.Q(("scope", "personal"), ("target_user__isnull", False))
                        ),
                        name="announcement_scope_matches_target",
                    ),
                ),
            },
        ),
    ]
