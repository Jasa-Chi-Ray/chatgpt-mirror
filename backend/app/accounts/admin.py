# -*- coding: utf-8 -*-
from django.contrib import admin
from django.utils import timezone
from django.contrib.auth.models import Group
from django.db.models import Q
from rest_framework.authtoken.models import TokenProxy

from app.accounts.models import Announcement, User
from app.accounts.target_security import can_manage_user, require_manage_user, managed_write
from app.accounts.names import ensure_username_available


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "is_active",
        "username",
        "isolated_session",
        "allow_multiple_sessions",
        "mcp_isolation",
        "skills_isolation",
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

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request,obj) and (obj is None or can_manage_user(request.user,obj))

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request,obj) and (obj is None or can_manage_user(request.user,obj))

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request,obj) and (obj is None or can_manage_user(request.user,obj))

    def save_model(self, request, obj, form, change):
        from app.accounts.views import revoke_user_sessions
        with managed_write(request.user) as actor:
            if change:
                current=User.objects.get(pk=obj.pk)
                require_manage_user(actor,current,destructive=not obj.is_active or bool(obj.expired_date and obj.expired_date<=timezone.localdate()))
                if current.username != obj.username:
                    ensure_username_available(obj.username)
                credentials_changed=current.password!=obj.password
            else:
                ensure_username_available(obj.username)
                credentials_changed=False
            super().save_model(request,obj,form,change)
            if credentials_changed or not obj.is_active:revoke_user_sessions(obj)

    def delete_model(self, request, obj):
        self.delete_queryset(request,User.objects.filter(pk=obj.pk))

    def delete_queryset(self, request, queryset):
        from app.accounts.target_security import managed_targets
        from app.accounts.views import revoke_user_sessions
        with managed_write(request.user) as actor:
            users=managed_targets(actor,list(queryset.values_list('pk',flat=True)),destructive=True)
            for user in users:revoke_user_sessions(user)
            queryset.delete()

    def get_readonly_fields(self, request, obj=None):
        if obj and (obj.is_staff or obj.is_superuser):
            return ("allow_multiple_sessions",)
        return ()


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "scope", "target_user", "is_active", "updated_at")
    list_filter = ("scope", "is_active")
    search_fields = ("title", "content", "target_user__username")


admin.site.unregister(Group)
admin.site.unregister(TokenProxy)
admin.site.site_header = "ChatGPT"
admin.site.site_title = "ChatGPT"
