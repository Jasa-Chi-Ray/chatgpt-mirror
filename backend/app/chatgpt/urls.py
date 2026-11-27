# -*- coding: utf-8 -*-
from django.urls import path

from app.chatgpt.views.chatgpt import ChatGPTAccountView, ChatGPTLoginView, ChatGPTAccountEnum, ChatGPTTokenExpiryView, \
    ChatGPTRefreshTokenView, ChatGPTLoginCountResetView
from app.chatgpt.views.gptcar import GptCarView, GptCarEnum, GptCarDetailView, GptCarUserAssignmentView
from app.chatgpt.views.health import AccountHealthSettingsView
from app.chatgpt.views.web_login import WebLoginView, WebLoginSyncView, WebLoginOwnersView

urlpatterns = [
    path("web-login", WebLoginView.as_view()),
    path("web-login/sync", WebLoginSyncView.as_view()),
    path("web-login/owners", WebLoginOwnersView.as_view()),
    path("health-settings", AccountHealthSettingsView.as_view()),
    path("enum", ChatGPTAccountEnum.as_view()),
    path("", ChatGPTAccountView.as_view()),
    path("token-expiry", ChatGPTTokenExpiryView.as_view()),
    path("refresh-token", ChatGPTRefreshTokenView.as_view()),
    path("reset-login-count", ChatGPTLoginCountResetView.as_view()),
    path("login", ChatGPTLoginView.as_view()),
    path("car", GptCarView.as_view()),
    path("car/<int:car_id>/detail", GptCarDetailView.as_view()),
    path("car/<int:car_id>/users", GptCarUserAssignmentView.as_view()),
    path("car-enum", GptCarEnum.as_view()),

]
