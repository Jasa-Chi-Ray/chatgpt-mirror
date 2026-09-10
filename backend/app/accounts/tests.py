from datetime import timedelta
from unittest.mock import Mock, call, patch

from django.db import connection
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from app.accounts.models import Announcement, User, VisitLog, GatewayRevocation
from app.accounts.views import (
    ChangePasswordView,
    ConversationTitlePrivacyView,
    CustomScriptConfigView,
    UserAccountView,
    UserConversationStatisticsView,
    UserSessionRevokeView,
    VisitLogView,
)
from app.accounts.authentication import AUTH_COOKIE_NAME, ExpiringCookieTokenAuthentication
from app.accounts.views.cfg import AccessControlView, PoliticalModerationConfigView
from app.accounts.views.announcements import AnnouncementAdminView, CurrentAnnouncementView
from app.accounts.views.login import (
    AccountLogin,
    AccountLogout,
    AccountRegister,
    UserFreeLoginView,
    verify_turnstile,
)
from app.accounts.views.backup import (
    GATEWAY_BACKUP_COLLECTIONS,
    GATEWAY_BACKUP_VERSION,
    _require_complete_gateway_backup,
    _restore_django_and_gateway,
    UnifiedBackupView,
)
from app.chatgpt.models import ChatgptAccount, ChatgptCar
from app.chatgpt.serializers import ShowChatgptTokenSerializer
from app.chatgpt.views.chatgpt import ChatGPTLoginView, ChatGPTLoginCountResetView
from app.chatgpt.views.gptcar import GptCarDetailView, GptCarUserAssignmentView
from app.settings import ADMIN_USERNAME, FREE_ACCOUNT_USERNAME
from app.utils import get_client_ip, req_gateway


class UnifiedBackupValidationTests(TestCase):
    def _gateway_backup(self):
        return {
            "version": GATEWAY_BACKUP_VERSION,
            **{name: [] for name in GATEWAY_BACKUP_COLLECTIONS},
        }

    def test_complete_gateway_backup_requires_matching_version_and_all_collections(self):
        payload = self._gateway_backup()
        _require_complete_gateway_backup(payload)

        payload["version"] = 1
        with self.assertRaises(ValidationError):
            _require_complete_gateway_backup(payload)

        payload = self._gateway_backup()
        payload.pop("gateway_sessions")
        with self.assertRaises(ValidationError):
            _require_complete_gateway_backup(payload)

    @patch("app.accounts.views.backup.req_gateway")
    def test_gateway_is_rolled_back_when_django_restore_fails(self, req_gateway):
        previous = self._gateway_backup()
        target = self._gateway_backup()
        req_gateway.side_effect = [previous, {"message": "restored"}, {"message": "rolled back"}]
        restore_django = Mock(side_effect=RuntimeError("django restore failed"))

        with self.assertRaisesRegex(RuntimeError, "django restore failed"):
            _restore_django_and_gateway(target, restore_django)

        self.assertEqual(
            req_gateway.call_args_list,
            [
                call("get", "/api/backup/export"),
                call("post", "/api/backup/restore", json=target),
                call("post", "/api/backup/restore", json=previous),
            ],
        )

    @patch("app.accounts.views.backup.req_gateway")
    def test_gateway_failure_also_attempts_rollback(self, req_gateway):
        previous = self._gateway_backup()
        target = self._gateway_backup()
        req_gateway.side_effect = [
            previous,
            RuntimeError("gateway restore failed"),
            {"message": "rolled back"},
        ]

        with self.assertRaisesRegex(RuntimeError, "gateway restore failed"):
            _restore_django_and_gateway(target, Mock())

        self.assertEqual(
            req_gateway.call_args_list[-1],
            call("post", "/api/backup/restore", json=previous),
        )


class SecurityRegressionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()

    def test_force_chat_mode_is_enabled_for_new_users(self):
        user = User.objects.create_user(username="work-mode-user", password="Strong-password-123!")
        self.assertTrue(user.force_chat_mode)

    @patch("app.accounts.views.req_gateway", side_effect=ValidationError("网关不可用"))
    def test_work_mode_sync_failure_is_not_reported_as_success(self, gateway):
        admin = User.objects.create_superuser(
            username="work-mode-admin",
            password="Strong-password-123!",
        )
        user = User.objects.create_user(
            username="work-mode-target",
            password="Strong-password-123!",
            force_chat_mode=False,
        )
        request = self.factory.post(
            "/0x/user/",
            {
                "username": user.username,
                "is_active": True,
                "isolated_session": True,
                "gptcar_list": [],
                "model_limit": [],
                "remark": "",
                "force_chat_mode": True,
            },
            format="json",
        )
        force_authenticate(request, user=admin)
        response = UserAccountView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        user.refresh_from_db()
        self.assertTrue(user.force_chat_mode)
        gateway.assert_called_once_with(
            "post",
            "/api/user-work-mode",
            json={"user_name": user.username, "force_chat_mode": True},
        )

    @patch("app.accounts.views.backup.req_gateway")
    @patch("app.accounts.views.req_gateway")
    @patch("app.accounts.views.cfg.req_gateway")
    def test_staff_cannot_access_root_security_controls(
        self, moderation_gateway, script_gateway, backup_gateway
    ):
        staff = User.objects.create_user(
            username="limited-staff",
            password="Strong-password-123!",
            is_staff=True,
        )
        for path, view in [
            ("/0x/user/political-moderation", PoliticalModerationConfigView),
            ("/0x/user/custom-scripts", CustomScriptConfigView),
            ("/0x/user/backup", UnifiedBackupView),
        ]:
            request = self.factory.get(path)
            force_authenticate(request, user=staff)
            self.assertEqual(view.as_view()(request).status_code, 403)
        moderation_gateway.assert_not_called()
        script_gateway.assert_not_called()
        backup_gateway.assert_not_called()

    @patch("app.accounts.views.req_gateway", return_value={"scripts": []})
    def test_superuser_can_access_root_security_controls(self, gateway):
        admin = User.objects.create_superuser(
            username="root-security-admin",
            password="Strong-password-123!",
        )
        request = self.factory.get("/0x/user/custom-scripts")
        force_authenticate(request, user=admin)
        self.assertEqual(CustomScriptConfigView.as_view()(request).status_code, 200)
        gateway.assert_called_once_with("get", "/api/custom-scripts")

    @patch("app.utils.requests.request")
    def test_gateway_requests_have_connect_and_read_timeouts(self, request_call):
        response = Mock(status_code=200)
        response.json.return_value = {"ok": True}
        request_call.return_value = response
        with patch("app.utils.GATEWAY_CONNECT_TIMEOUT_SECONDS", 1.5), patch(
            "app.utils.GATEWAY_READ_TIMEOUT_SECONDS", 2.5
        ):
            self.assertEqual(req_gateway("get", "/api/test"), {"ok": True})
        self.assertEqual(request_call.call_args.kwargs["timeout"], (1.5, 2.5))

    def test_empty_account_pool_is_fail_closed(self):
        self.assertFalse(ChatgptAccount.get_by_gptcar_list([]).exists())

    def test_admin_can_view_users_assigned_to_account_pool(self):
        admin = User.objects.create_superuser(
            username="pool-detail-admin",
            password="Strong-password-123!",
        )
        car_one = ChatgptCar.objects.create(
            car_name="pool-detail-one",
            gpt_account_list=[],
            created_time=1,
            updated_time=1,
        )
        car_two = ChatgptCar.objects.create(
            car_name="pool-detail-two",
            gpt_account_list=[],
            created_time=1,
            updated_time=1,
        )
        User.objects.create_user(username="pool-user-one", gptcar_list=[car_one.id])
        User.objects.create_user(username="pool-user-two", gptcar_list=[car_two.id])
        User.objects.create_user(username="pool-user-both", gptcar_list=[car_one.id, car_two.id])

        request = self.factory.get(f"/0x/chatgpt/car/{car_one.id}/detail")
        force_authenticate(request, user=admin)
        response = GptCarDetailView.as_view()(request, car_id=car_one.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["assigned_users"]), 2)
        self.assertEqual(
            {item["username"] for item in response.data["assigned_users"]},
            {"pool-user-one", "pool-user-both"},
        )
        self.assertEqual(
            {item["username"] for item in response.data["available_users"]},
            {"pool-user-two"},
        )

        user_two = User.objects.get(username="pool-user-two")
        request = self.factory.post(
            f"/0x/chatgpt/car/{car_one.id}/users",
            {"user_ids": [user_two.id]},
            format="json",
        )
        force_authenticate(request, user=admin)
        response = GptCarUserAssignmentView.as_view()(request, car_id=car_one.id)
        user_two.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn(car_one.id, user_two.gptcar_list)
        self.assertIn(car_two.id, user_two.gptcar_list)

        user_one = User.objects.get(username="pool-user-one")
        request = self.factory.delete(
            f"/0x/chatgpt/car/{car_one.id}/users",
            {"user_ids": [user_one.id]},
            format="json",
        )
        force_authenticate(request, user=admin)
        response = GptCarUserAssignmentView.as_view()(request, car_id=car_one.id)
        user_one.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(car_one.id, user_one.gptcar_list)

    def test_user_expired_date_can_be_assigned_and_cleared(self):
        admin = User.objects.create_superuser(
            username="expiry-admin",
            password="Strong-password-123!",
        )
        user = User.objects.create_user(
            username="expiry-user",
            password="Strong-password-123!",
        )
        expires_at = timezone.localdate() + timedelta(days=30)
        payload = {
            "username": user.username,
            "is_active": True,
            "isolated_session": True,
            "gptcar_list": [],
            "model_limit": [],
            "remark": "",
            "expired_date": expires_at.isoformat(),
        }

        request = self.factory.post("/0x/user/", payload, format="json")
        force_authenticate(request, user=admin)
        response = UserAccountView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.expired_date, expires_at)

        payload["expired_date"] = None
        request = self.factory.post("/0x/user/", payload, format="json")
        force_authenticate(request, user=admin)
        response = UserAccountView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertIsNone(user.expired_date)

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

    @patch("app.accounts.views.cfg.req_gateway", return_value={"paths": ["/pricing"]})
    def test_access_control_forwards_custom_paths(self, req_gateway):
        admin = User.objects.create_superuser(username="path-admin", password="password-123")
        request = self.factory.post(
            "/0x/user/access-control", {"paths": ["pricing"]}, format="json"
        )
        force_authenticate(request, user=admin)
        response = AccessControlView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        req_gateway.assert_called_once_with(
            "post", "/api/blocked-paths", json={"paths": ["pricing"]}
        )

    @patch("app.accounts.revocations.req_gateway", return_value={"revoked": True})
    def test_logout_revokes_drf_and_gateway_sessions(self, req_gateway):
        user = User.objects.create_user(username="logout-user", password="password-123")
        token = Token.objects.create(user=user)
        request = self.factory.post("/0x/user/logout", {}, format="json")
        request.COOKIES[AUTH_COOKIE_NAME] = token.key
        force_authenticate(request, user=user, token=token)
        with self.captureOnCommitCallbacks(execute=True):
            response = AccountLogout.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(key=token.key).exists())
        req_gateway.assert_called_once()
        self.assertEqual(req_gateway.call_args.args, ("post", "/api/revoke-authorization"))
        self.assertEqual(req_gateway.call_args.kwargs["json"]["subject"], "logout-user")
        self.assertFalse(GatewayRevocation.objects.exists())

    @patch("app.accounts.revocations.req_gateway", return_value={"revoked": True})
    def test_admin_can_revoke_user_sessions(self, req_gateway):
        admin = User.objects.create_superuser(
            username="revoke-admin", password="Strong-password-123!"
        )
        user = User.objects.create_user(
            username="revoke-user", password="Strong-password-123!"
        )
        token = Token.objects.create(user=user)
        request = self.factory.post(
            "/0x/user/revoke-sessions", {"user_id": user.id}, format="json"
        )
        force_authenticate(request, user=admin)
        req_gateway.side_effect = lambda *_args, **_kwargs: (
            self.assertFalse(Token.objects.filter(key=token.key).exists())
            or {"revoked": True}
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = UserSessionRevokeView.as_view()(request)
        # TestCase's outer transaction defers delivery until the captured commit.
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Token.objects.filter(key=token.key).exists())
        req_gateway.assert_called_once()
        self.assertEqual(req_gateway.call_args.args, ("post", "/api/revoke-authorization"))
        self.assertEqual(req_gateway.call_args.kwargs["json"]["subject"], "revoke-user")
        self.assertFalse(GatewayRevocation.objects.exists())

    @patch("app.accounts.revocations.req_gateway", side_effect=ValidationError("网关不可用"))
    def test_revoke_sessions_removes_drf_token_when_gateway_revoke_fails(self, _req_gateway):
        admin = User.objects.create_superuser(
            username="revoke-failure-admin", password="Strong-password-123!"
        )
        user = User.objects.create_user(
            username="revoke-failure-user", password="Strong-password-123!"
        )
        token = Token.objects.create(user=user)
        request = self.factory.post(
            "/0x/user/revoke-sessions", {"user_id": user.id}, format="json"
        )
        force_authenticate(request, user=admin)

        response = UserSessionRevokeView.as_view()(request)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    @patch("app.accounts.views.req_gateway")
    def test_normal_user_cannot_revoke_sessions(self, req_gateway):
        user = User.objects.create_user(
            username="revoke-normal-user", password="Strong-password-123!"
        )
        target = User.objects.create_user(
            username="revoke-target-user", password="Strong-password-123!"
        )
        request = self.factory.post(
            "/0x/user/revoke-sessions", {"user_id": target.id}, format="json"
        )
        force_authenticate(request, user=user)

        response = UserSessionRevokeView.as_view()(request)

        self.assertEqual(response.status_code, 403)
        req_gateway.assert_not_called()

    def test_stale_auth_cookie_does_not_block_public_login_with_csrf_403(self):
        user = User.objects.create_user(username="stale-login", password="Strong-password-123!")
        token = Token.objects.create(user=user)
        request = self.factory.post(
            "/0x/user/login",
            {"username": "stale-login", "password": "wrong-password"},
            format="json",
            HTTP_COOKIE=f"{AUTH_COOKIE_NAME}={token.key}",
        )

        response = AccountLogin.as_view()(request)

        self.assertEqual(response.status_code, 400)

    @override_settings(CSRF_TRUSTED_ORIGINS=["https://mirror.example"])
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", False)
    def test_admin_login_issues_csrf_cookie_for_unsafe_api_requests(self):
        User.objects.create_superuser(username="csrf-admin", password="Strong-password-123!")
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/0x/user/version-cfg").data["csrf_token"]

        login = client.post(
            "/0x/user/login",
            {"username": "csrf-admin", "password": "Strong-password-123!"},
            format="json",
            HTTP_USER_AGENT="security-regression-test",
            HTTP_ORIGIN="https://mirror.example",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login.status_code, 200)
        login = client.post("/0x/user/login-confirm", {"login_ticket": login.data["login_ticket"]},
                            format="json", HTTP_X_CSRFTOKEN=csrf, HTTP_USER_AGENT="security-regression-test")
        self.assertEqual(login.status_code, 200)
        self.assertIn("csrftoken", login.cookies)
        self.assertTrue(login.data["csrf_token"])

        rejected = client.post(
            "/0x/user/",
            {},
            format="json",
            HTTP_ORIGIN="https://mirror.example",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(rejected.status_code, 403)

        me = client.get("/0x/user/me")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.data["csrf_token"])

        response = client.post(
            "/0x/user/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=me.data["csrf_token"],
            HTTP_ORIGIN="https://mirror.example",
            HTTP_REFERER="https://mirror.example/admin/",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertNotEqual(response.status_code, 403)

        untrusted = client.post(
            "/0x/user/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=me.data["csrf_token"],
            HTTP_ORIGIN="https://untrusted.example",
            HTTP_REFERER="https://untrusted.example/admin/",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertEqual(untrusted.status_code, 403)

    @override_settings(DJANGO_ALLOW_ALL_ORIGINS=True, ALLOWED_HOSTS=["*"])
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", False)
    def test_allow_all_origins_accepts_unlisted_origin_with_csrf_token(self):
        User.objects.create_superuser(username="open-origin-admin", password="Strong-password-123!")
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/0x/user/version-cfg").data["csrf_token"]

        login = client.post(
            "/0x/user/login",
            {"username": "open-origin-admin", "password": "Strong-password-123!"},
            format="json",
            HTTP_USER_AGENT="security-regression-test",
            HTTP_ORIGIN="https://unlisted.example",
            HTTP_X_FORWARDED_PROTO="https",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(login.status_code, 200)
        login = client.post("/0x/user/login-confirm", {"login_ticket": login.data["login_ticket"]},
                            format="json", HTTP_X_CSRFTOKEN=csrf, HTTP_USER_AGENT="security-regression-test")
        self.assertEqual(login.status_code, 200)

        response = client.post(
            "/0x/user/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=login.data["csrf_token"],
            HTTP_ORIGIN="https://another-unlisted.example",
            HTTP_REFERER="https://another-unlisted.example/admin/",
            HTTP_X_FORWARDED_PROTO="https",
        )
        self.assertNotEqual(response.status_code, 403)

    @patch("app.accounts.views.login.save_visit_log")
    def test_free_login_keeps_shared_token_but_rotates_visitor_subject(self, _save_visit_log):
        User.objects.create_user(username=FREE_ACCOUNT_USERNAME, password="password-123")
        results = []
        for _ in range(2):
            client = APIClient(enforce_csrf_checks=True)
            csrf = client.get("/0x/user/version-cfg").data["csrf_token"]
            prepared = client.post("/0x/user/login-free", {}, format="json", HTTP_X_CSRFTOKEN=csrf)
            results.append(client.post("/0x/user/login-confirm", {"login_ticket": prepared.data["login_ticket"]},
                                       format="json", HTTP_X_CSRFTOKEN=csrf))
        first, second = results
        self.assertNotIn("admin_token", first.data)
        self.assertEqual(
            first.cookies[AUTH_COOKIE_NAME].value,
            second.cookies[AUTH_COOKIE_NAME].value,
        )
        self.assertNotEqual(
            first.cookies["free_session"].value,
            second.cookies["free_session"].value,
        )
        self.assertTrue(first.cookies["free_session"]["httponly"])
        self.assertTrue(first.cookies[AUTH_COOKIE_NAME]["httponly"])

    @override_settings(API_TOKEN_TTL_SECONDS=60)
    def test_expired_drf_token_is_rejected(self):
        user = User.objects.create_user(username="expired-token", password="password-123")
        token = Token.objects.create(user=user)
        Token.objects.filter(pk=token.pk).update(created=timezone.now() - timedelta(seconds=61))
        token.refresh_from_db()
        with patch("app.accounts.revocations.req_gateway") as req_gateway:
            with self.captureOnCommitCallbacks(execute=True), self.assertRaises(Exception):
                request = self.factory.get(
                    "/0x/user/me",
                    HTTP_AUTHORIZATION=f"Token {token.key}",
                )
                ExpiringCookieTokenAuthentication().authenticate(request)
            # The grant is already expired; the gateway lease cannot outlive it.
            req_gateway.assert_not_called()
            self.assertFalse(Token.objects.filter(user=user).exists())
            self.assertFalse(GatewayRevocation.objects.filter(subject=user.username).exists())

    @patch("app.accounts.views.login.req_gateway")
    @patch("app.accounts.views.login.ALLOW_REGISTER", True)
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", False)
    def test_registration_conflict_is_checked_before_upstream_write(self, req_gateway):
        User.objects.create_user(username="existing-user", password="Strong-password-123!")
        request = self.factory.post(
            "/0x/user/register",
            {
                "username": "existing-user",
                "password": "Another-strong-password-123!",
                "chatgpt_token": "upstream-secret",
            },
            format="json",
        )
        response = AccountRegister.as_view()(request)
        self.assertEqual(response.status_code, 400)
        req_gateway.assert_not_called()

    @patch("app.accounts.views.req_gateway", return_value={"message": "ok"})
    def test_password_change_revokes_old_token_and_issues_new_cookie(self, _req_gateway):
        user = User.objects.create_user(
            username="change-password-user",
            password="Old-strong-password-123!",
        )
        old_token = Token.objects.create(user=user)
        request = self.factory.post(
            "/0x/user/change-password",
            {
                "current_password": "Old-strong-password-123!",
                "new_password": "New-strong-password-456!",
            },
            format="json",
        )
        force_authenticate(request, user=user, token=old_token)
        response = ChangePasswordView.as_view()(request)
        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(user.check_password("New-strong-password-456!"))
        self.assertFalse(user.check_password("Old-strong-password-123!"))
        self.assertFalse(Token.objects.filter(key=old_token.key).exists())
        self.assertTrue(response.cookies[AUTH_COOKIE_NAME]["httponly"])

    def test_chatgpt_credentials_are_encrypted_at_rest(self):
        account = ChatgptAccount.objects.create(
            chatgpt_username="encrypted@example.com",
            plan_type="plus",
            access_token="plain-access-secret",
            session_token="plain-session-secret",
            extra_cookies=[{"name": "session", "value": "plain-cookie-secret"}],
            created_time=1,
            updated_time=1,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT access_token, session_token, extra_cookies FROM chatgpt_chatgptaccount WHERE id = %s",
                [account.id],
            )
            stored = cursor.fetchone()
        self.assertTrue(stored[0].startswith("enc:v1:"))
        self.assertTrue(stored[1].startswith("enc:v1:"))
        self.assertTrue(stored[2].startswith("enc:v1:"))
        self.assertNotIn("plain", "".join(stored))

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

    @patch("app.chatgpt.views.chatgpt.req_gateway", return_value={"login_url": "/handoff"})
    def test_successful_gateway_login_increments_upstream_login_count(self, _req_gateway):
        account = ChatgptAccount.objects.create(
            chatgpt_username="login-count@example.com",
            plan_type="plus",
            access_token="secret-access",
            access_token_valid=True,
            login_count=3,
            created_time=1,
            updated_time=1,
        )
        car = ChatgptCar.objects.create(
            car_name="login-count-car",
            gpt_account_list=[account.id],
            created_time=1,
            updated_time=1,
        )
        user = User.objects.create_user(
            username="login-count-user",
            password="Strong-password-123!",
            gptcar_list=[car.id],
        )
        request = self.factory.post(
            "/0x/chatgpt/login",
            {"chatgpt_id": account.id, "login_mode": "api"},
            format="json",
            HTTP_USER_AGENT="test-browser",
        )
        force_authenticate(request, user=user)
        response = ChatGPTLoginView.as_view()(request)
        account.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(account.login_count, 4)

    def test_admin_can_reset_upstream_login_count(self):
        admin = User.objects.create_superuser(
            username="login-count-admin",
            password="Strong-password-123!",
        )
        account = ChatgptAccount.objects.create(
            chatgpt_username="reset-count@example.com",
            plan_type="plus",
            access_token="secret-access",
            login_count=9,
            created_time=1,
            updated_time=1,
        )
        request = self.factory.post(
            "/0x/chatgpt/reset-login-count",
            {"id": account.id},
            format="json",
        )
        force_authenticate(request, user=admin)
        response = ChatGPTLoginCountResetView.as_view()(request)
        account.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(account.login_count, 0)

    def test_user_controls_title_visibility_and_admin_receives_no_hidden_title(self):
        admin = User.objects.create_superuser(
            username="statistics-admin",
            password="Strong-password-123!",
        )
        user = User.objects.create_user(
            username="statistics-user",
            password="Strong-password-123!",
        )
        privacy_request = self.factory.post(
            "/0x/user/conversation-title-privacy",
            {"allow_admin_view_conversation_titles": False},
            format="json",
        )
        force_authenticate(privacy_request, user=user)
        privacy_response = ConversationTitlePrivacyView.as_view()(privacy_request)
        self.assertEqual(privacy_response.status_code, 200)

        with patch("app.accounts.views.req_gateway", return_value={
            "conversation_count": 1,
            "message_count": 2,
            "model_message_counts": {"gpt-5": 2},
            "conversations": [{
                "conversation_id": "uuid-from-official-path",
                "title": "管理员不应收到此标题",
                "message_count": 2,
            }],
        }):
            request = self.factory.get(
                f"/0x/user/conversation-statistics/{user.id}"
            )
            force_authenticate(request, user=admin)
            response = UserConversationStatisticsView.as_view()(request, user_id=user.id)
        self.assertFalse(response.data["title_visible"])
        self.assertEqual(
            response.data["conversations"][0]["display_title"],
            "uuid-from-official-path",
        )
        self.assertNotIn("title", response.data["conversations"][0])

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
            "challenge_ts": timezone.now().isoformat(),
            "hostname": "mirror.example.com",
        }
        request = self.factory.post(
            "/0x/user/login",
            {"turnstile_token": "test-token"},
            format="json",
        )
        request.data = {"turnstile_token": "test-token"}

        verify_turnstile(request, "login")

        post.assert_called_once()
        post.return_value.raise_for_status.assert_called_once()
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

    @patch("app.accounts.views.login.TURNSTILE_SECRET_KEY", "test-secret")
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", True)
    @patch("app.accounts.views.login.requests.post")
    def test_turnstile_rejects_expired_token(self, post):
        post.return_value.json.return_value = {
            "success": True,
            "action": "login",
            "challenge_ts": (timezone.now() - timedelta(seconds=301)).isoformat(),
            "hostname": "mirror.example.com",
        }
        request = self.factory.post(
            "/0x/user/login",
            {"turnstile_token": "expired-token"},
            format="json",
        )
        request.data = {"turnstile_token": "expired-token"}

        with self.assertRaises(ValidationError):
            verify_turnstile(request, "login")

    @patch("app.accounts.views.login.TURNSTILE_SECRET_KEY", "test-secret")
    @patch("app.accounts.views.login.TURNSTILE_ENABLED", True)
    @patch("app.accounts.views.login.requests.post")
    def test_turnstile_requires_boolean_success(self, post):
        post.return_value.json.return_value = {
            "success": "true",
            "action": "login",
            "challenge_ts": timezone.now().isoformat(),
            "hostname": "mirror.example.com",
        }
        request = self.factory.post(
            "/0x/user/login",
            {"turnstile_token": "malformed-token"},
            format="json",
        )
        request.data = {"turnstile_token": "malformed-token"}

        with self.assertRaises(ValidationError):
            verify_turnstile(request, "login")


class AnnouncementTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.admin = User.objects.create_superuser(
            username="announcement-admin",
            password="Strong-password-123!",
        )
        self.user = User.objects.create_user(
            username="announcement-user",
            password="Strong-password-123!",
        )
        self.other_user = User.objects.create_user(
            username="announcement-other",
            password="Strong-password-123!",
        )

    def test_admin_can_publish_global_and_personal_announcements(self):
        global_request = self.factory.post(
            "/0x/user/announcements",
            {
                "title": "全局通知",
                "content": "所有用户都可以看到",
                "scope": "global",
                "is_active": True,
            },
            format="json",
        )
        force_authenticate(global_request, user=self.admin)
        global_response = AnnouncementAdminView.as_view()(global_request)

        personal_request = self.factory.post(
            "/0x/user/announcements",
            {
                "title": "个人通知",
                "content": "只有目标用户可以看到",
                "scope": "personal",
                "target_user_id": self.user.id,
                "is_active": True,
            },
            format="json",
        )
        force_authenticate(personal_request, user=self.admin)
        personal_response = AnnouncementAdminView.as_view()(personal_request)

        self.assertEqual(global_response.status_code, 201)
        self.assertEqual(personal_response.status_code, 201)
        self.assertIsNone(Announcement.objects.get(id=global_response.data["id"]).target_user)
        self.assertEqual(
            Announcement.objects.get(id=personal_response.data["id"]).target_user,
            self.user,
        )

    def test_current_announcements_only_include_global_and_current_user(self):
        global_announcement = Announcement.objects.create(
            title="全局通知",
            content="全局内容",
            scope=Announcement.SCOPE_GLOBAL,
            created_by=self.admin,
        )
        own_announcement = Announcement.objects.create(
            title="你的通知",
            content="个人内容",
            scope=Announcement.SCOPE_PERSONAL,
            target_user=self.user,
            created_by=self.admin,
        )
        Announcement.objects.create(
            title="其他人的通知",
            content="不应返回",
            scope=Announcement.SCOPE_PERSONAL,
            target_user=self.other_user,
            created_by=self.admin,
        )
        Announcement.objects.create(
            title="停用通知",
            content="不应返回",
            scope=Announcement.SCOPE_GLOBAL,
            is_active=False,
            created_by=self.admin,
        )

        request = self.factory.get("/0x/user/announcements/current")
        force_authenticate(request, user=self.user)
        response = CurrentAnnouncementView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in response.data["global"]],
            [global_announcement.id],
        )
        self.assertEqual(
            [item["id"] for item in response.data["personal"]],
            [own_announcement.id],
        )

    def test_normal_user_cannot_manage_announcements(self):
        request = self.factory.get("/0x/user/announcements")
        force_authenticate(request, user=self.user)
        response = AnnouncementAdminView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_schedule_history_and_admin_login_visibility(self):
        now = timezone.now()
        history = Announcement.objects.create(
            title="已结束公告",
            content="历史内容",
            scope=Announcement.SCOPE_GLOBAL,
            start_at=now - timedelta(days=2),
            end_at=now - timedelta(days=1),
            display_timezone="Asia/Shanghai",
            created_by=self.admin,
        )
        Announcement.objects.create(
            title="待发布公告",
            content="未来内容",
            scope=Announcement.SCOPE_GLOBAL,
            start_at=now + timedelta(days=1),
            created_by=self.admin,
        )

        user_request = self.factory.get("/0x/user/announcements/current")
        force_authenticate(user_request, user=self.user)
        user_response = CurrentAnnouncementView.as_view()(user_request)
        self.assertEqual([item["id"] for item in user_response.data["history"]], [history.id])
        self.assertFalse(user_response.data["global"])

        admin_request = self.factory.get("/0x/user/announcements/current")
        force_authenticate(admin_request, user=self.admin)
        admin_response = CurrentAnnouncementView.as_view()(admin_request)
        self.assertEqual(admin_response.data, {"global": [], "personal": [], "history": []})

    def test_announcement_end_time_must_be_after_start_time(self):
        now = timezone.now()
        request = self.factory.post(
            "/0x/user/announcements",
            {
                "title": "错误时间",
                "content": "内容",
                "scope": "global",
                "start_at": now.isoformat(),
                "end_at": (now - timedelta(minutes=1)).isoformat(),
                "display_timezone": "Asia/Shanghai",
            },
            format="json",
        )
        force_authenticate(request, user=self.admin)
        response = AnnouncementAdminView.as_view()(request)
        self.assertEqual(response.status_code, 400)
