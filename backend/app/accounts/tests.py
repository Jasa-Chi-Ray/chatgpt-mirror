from unittest.mock import patch

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory, force_authenticate

from app.accounts.models import User, VisitLog
from app.accounts.views import VisitLogView
from app.accounts.views.cfg import AccessControlView
from app.accounts.views.login import AccountLogout, UserFreeLoginView, verify_turnstile
from app.chatgpt.models import ChatgptAccount
from app.chatgpt.serializers import ShowChatgptTokenSerializer
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME
from app.utils import get_client_ip


class SecurityRegressionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_empty_account_pool_is_fail_closed(self):
        self.assertFalse(ChatgptAccount.get_by_gptcar_list([]).exists())

    def test_client_ip_prefers_gateway_forwarded_address(self):
        request = self.factory.get(
            "/0x/user/visit-log",
            HTTP_X_CHATGPT_MIRROR_CLIENT_IP="203.0.113.9",
            HTTP_X_FORWARDED_FOR="172.18.0.1",
            REMOTE_ADDR="172.18.0.2",
        )
        self.assertEqual(get_client_ip(request), "203.0.113.9")

    def test_client_ip_ignores_invalid_values_and_uses_remote_address(self):
        request = self.factory.get(
            "/0x/user/visit-log",
            HTTP_X_CHATGPT_MIRROR_CLIENT_IP="invalid",
            REMOTE_ADDR="2001:db8::9",
        )
        self.assertEqual(get_client_ip(request), "2001:db8::9")

    def test_access_control_requires_admin(self):
        user = User.objects.create_user(username="normal-user", password="password-123")
        request = self.factory.post("/0x/user/access-control", {"hash_paths": []}, format="json")
        force_authenticate(request, user=user)
        response = AccessControlView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    @patch("app.accounts.views.login.req_gateway", return_value={"message": "退出成功"})
    def test_logout_revokes_drf_and_gateway_sessions(self, req_gateway):
        user = User.objects.create_user(username="logout-user", password="password-123")
        token = Token.objects.create(user=user)
        request = self.factory.post("/0x/user/logout", {}, format="json")
        force_authenticate(request, user=user, token=token)
        response = AccountLogout.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(key=token.key).exists())
        req_gateway.assert_called_once_with(
            "post",
            "/api/logout",
            json={"user_name": "logout-user"},
        )

    @patch("app.accounts.views.login.save_visit_log")
    def test_free_login_keeps_shared_token_but_rotates_visitor_subject(self, _save_visit_log):
        User.objects.create_user(username=FREE_ACCOUNT_USERNAME, password="password-123")
        view = UserFreeLoginView.as_view()
        first = view(self.factory.post("/0x/user/login-free", {}, format="json"))
        second = view(self.factory.post("/0x/user/login-free", {}, format="json"))
        self.assertEqual(first.data["admin_token"], second.data["admin_token"])
        self.assertNotEqual(
            first.cookies["free_session"].value,
            second.cookies["free_session"].value,
        )
        self.assertTrue(first.cookies["free_session"]["httponly"])

    def test_account_serializer_excludes_raw_credentials(self):
        account = ChatgptAccount.objects.create(
            chatgpt_username="shared@example.com",
            plan_type="plus",
            access_token="secret-access",
            session_token="secret-session",
            refresh_token="secret-refresh",
            refresh_client_id="secret-client",
            extra_cookies=[{"name": "secret", "value": "cookie"}],
            created_time=1,
            updated_time=1,
        )
        data = ShowChatgptTokenSerializer(account).data
        for field in (
            "access_token",
            "session_token",
            "refresh_token",
            "refresh_client_id",
            "extra_cookies",
        ):
            self.assertNotIn(field, data)

    def test_clear_visit_logs_preserves_admin_login_logs(self):
        admin = User.objects.create_superuser(username="log-admin", password="password-123")
        VisitLog.objects.create(
            username=ADMIN_USERNAME,
            log_type="login",
            created_at=1,
            ip="127.0.0.1",
            user_agent="test",
        )
        VisitLog.objects.create(
            username=ADMIN_USERNAME,
            log_type="logout",
            created_at=2,
            ip="127.0.0.1",
            user_agent="test",
        )
        VisitLog.objects.create(
            username="normal-user",
            log_type="login",
            created_at=3,
            ip="127.0.0.1",
            user_agent="test",
        )

        request = self.factory.delete("/0x/user/visit-log")
        force_authenticate(request, user=admin)
        response = VisitLogView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["deleted_count"], 2)
        self.assertEqual(response.data["protected_count"], 1)
        self.assertEqual(VisitLog.objects.count(), 1)
        self.assertTrue(
            VisitLog.objects.filter(username=ADMIN_USERNAME, log_type="login").exists()
        )

    @patch("app.accounts.views.login.TURNSTILE_SECRET_KEY", "test-secret")
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", True)
    @patch("app.accounts.views.login.requests.post")
    def test_turnstile_validation_checks_action(self, post):
        post.return_value.json.return_value = {
            "success": True,
            "action": "login",
        }
        request = self.factory.post(
            "/0x/user/login",
            {"turnstile_token": "test-token"},
            format="json",
        )
        request.data = {"turnstile_token": "test-token"}

        verify_turnstile(request, "login")

        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["data"]["secret"], "test-secret")
        self.assertEqual(post.call_args.kwargs["data"]["response"], "test-token")

    @patch("app.accounts.views.login.TURNSTILE_SECRET_KEY", "test-secret")
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", True)
    @patch("app.accounts.views.login.requests.post")
    def test_turnstile_rejects_wrong_action(self, post):
        post.return_value.json.return_value = {
            "success": True,
            "action": "register",
        }
        request = self.factory.post(
            "/0x/user/login",
            {"turnstile_token": "test-token"},
            format="json",
        )
        request.data = {"turnstile_token": "test-token"}

        with self.assertRaises(ValidationError):
            verify_turnstile(request, "login")
