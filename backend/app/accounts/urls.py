# -*- coding: utf-8 -*-
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from app.accounts.views import UserAccountView, UserRelateGPTCarView, VisitLogView, BatchModelLimit, \
    UserChatGPTAccountList, GetMirrorToken, MirrorProxyConfigView, MirrorProxyTestView, CustomScriptConfigView
from app.accounts.views import BatchUserActionView, CurrentUserView, ChangePasswordView, QuotaView, OperationsOverviewView
from app.accounts.views.login import AccountLogin, AccountLogout, UserFreeLoginView, AccountRegister
from app.accounts.views.cfg import VersionConfig, AccessControlView
from app.accounts.views.backup import UnifiedBackupView

urlpatterns = [
    path("", UserAccountView.as_view()),
    path("version-cfg", VersionConfig.as_view()),
    path("get-mirror-token", GetMirrorToken.as_view()),
    path("register", AccountRegister.as_view()),
    path("login-free", UserFreeLoginView.as_view()),
    path("chatgpt-list", UserChatGPTAccountList.as_view()),
    path("batch-model-limit", BatchModelLimit.as_view()),
    path("proxy-config", MirrorProxyConfigView.as_view()),
    path("proxy-config/test", MirrorProxyTestView.as_view()),
    path("custom-scripts", CustomScriptConfigView.as_view()),
    path("relat-gptcar", UserRelateGPTCarView.as_view()),
    path("login", csrf_exempt(AccountLogin.as_view())),
    path("logout", AccountLogout.as_view()),
    path("visit-log", VisitLogView.as_view()),
    path("access-control", AccessControlView.as_view()),
    path("me", CurrentUserView.as_view()),
    path("change-password", ChangePasswordView.as_view()),
    path("quota", QuotaView.as_view()),
    path("overview", OperationsOverviewView.as_view()),
    path("batch", BatchUserActionView.as_view()),
    path("backup", UnifiedBackupView.as_view()),
]
