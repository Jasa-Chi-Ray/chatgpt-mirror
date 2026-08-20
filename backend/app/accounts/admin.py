# -*- coding: utf-8 -*-
from django.contrib import admin
from django.contrib.auth.models import Group
from django.db.models import Q
from rest_framework.authtoken.models import TokenProxy

from app.accounts.models import Announcement, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "is_active",
        "username",
        "isolated_session",
        "remark",
        "last_login",
    )
    exclude = (
        # "password",
        "user_permissions",
        "last_name",
        "last_login",
        "is_staff",
        "is_superuser",
        "date_joined",
        "email",
        "groups",
    )


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "scope", "target_user", "is_active", "updated_at")
    list_filter = ("scope", "is_active")
    search_fields = ("title", "content", "target_user__username")


admin.site.unregister(Group)
admin.site.unregister(TokenProxy)
admin.site.site_header = "ChatGPT"
admin.site.site_title = "ChatGPT"
