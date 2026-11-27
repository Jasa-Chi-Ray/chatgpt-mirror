"""Shared object authorization for every administrator-managed user mutation."""
from contextlib import contextmanager
from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from app.accounts.models import User


def can_manage_user(actor, target):
    return bool(actor and actor.is_active and (not actor.expired_date or actor.expired_date > timezone.localdate()) and (actor.is_superuser or
        (actor.is_staff and not target.is_staff and not target.is_superuser)))


def require_manage_user(actor, target, *, destructive=False):
    if not can_manage_user(actor, target):
        raise PermissionDenied('没有管理此账号的权限')
    if destructive and target.username == settings.ADMIN_USERNAME:
        raise PermissionDenied('初始化管理员不能停用或删除')
    if destructive and target.is_superuser and target.is_active and not User.objects.filter(
            is_superuser=True,is_staff=True,is_active=True).filter(Q(expired_date__isnull=True)|Q(expired_date__gt=timezone.localdate())).exclude(pk=target.pk).exists():
        raise PermissionDenied('必须保留至少一个有效超级管理员')
    return target


@contextmanager
def managed_write(actor):
    # The no-op write obtains a real SQLite write lock before reading roles.
    # Privileged rows are locked in a consistent order on row-locking databases.
    with transaction.atomic():
        list(User.objects.select_for_update().filter(Q(pk=actor.pk)|Q(is_superuser=True)).order_by('pk').values_list('pk',flat=True))
        if not User.objects.filter(pk=actor.pk,is_active=True).update(last_login=F('last_login')):
            raise PermissionDenied('管理员登录状态已改变')
        current=User.objects.get(pk=actor.pk)
        if current.expired_date and current.expired_date <= timezone.localdate():
            raise PermissionDenied('管理员账号已到期')
        if not (current.is_staff or current.is_superuser):
            raise PermissionDenied('需要管理员权限')
        yield current


def managed_targets(actor, ids, *, destructive=False):
    ids=list(dict.fromkeys(ids));users=list(User.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    if len(users)!=len(ids):raise ValidationError({'user_id_list':'部分用户不存在'})
    for target in users:
        require_manage_user(actor,target,destructive=destructive)
    if destructive and any(user.is_superuser and user.is_active for user in users):
        survivors=User.objects.filter(is_superuser=True,is_staff=True,is_active=True).exclude(pk__in=ids)
        if not survivors.filter(Q(expired_date__isnull=True)|Q(expired_date__gt=timezone.localdate())).exists():
            raise PermissionDenied('必须保留至少一个有效超级管理员')
    return users


def save_managed_user(actor, user, *, update_fields=None):
    with managed_write(actor) as current:
        target=User.objects.get(pk=user.pk)
        require_manage_user(current,target,destructive=not user.is_active or bool(user.expired_date and user.expired_date<=timezone.localdate()))
        user.is_staff=target.is_staff;user.is_superuser=target.is_superuser
        user.save(update_fields=update_fields)
