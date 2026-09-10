from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from django.db import transaction
from django.core.management import call_command
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient, APIRequestFactory

from app.accounts.authentication import AUTH_COOKIE_NAME
from app.accounts.models import PendingLogin, User, VisitorSession, GatewayRevocation
from app.accounts.session_authority import authorization_is_active, gateway_authorization, authorization_details, authorization_version
from app.accounts.views import revoke_user_sessions
from app.accounts.views.login import LoginIpRateThrottle
from app.settings import FREE_ACCOUNT_USERNAME
from app.utils import get_request_subject


class GatewayLeaseTests(TransactionTestCase):
    def setUp(self):
        self.gateway = patch("app.accounts.revocations.req_gateway", return_value={"revoked": True}).start()
        self.addCleanup(patch.stopall)
        self.user = User.objects.create_user(username="lease-user", password="test-password")
        self.token = Token.objects.create(user=self.user)

    def grant(self):
        self.user.refresh_from_db()
        return gateway_authorization(SimpleNamespace(user=self.user, auth=self.token, COOKIES={}))

    def test_lease_is_60_minutes_and_uses_one_user_query(self):
        now = timezone.now()
        with patch("app.accounts.session_authority.timezone.now", return_value=now):
            grant = self.grant()
            with self.assertNumQueries(1):
                details = authorization_details(grant, self.user.username)
        self.assertEqual(details["expires_at"], int((now + timedelta(hours=1)).timestamp()))

    @override_settings(API_TOKEN_TTL_SECONDS=30)
    def test_lease_cannot_outlive_login(self):
        details = authorization_details(self.grant(), self.user.username)
        self.assertLessEqual(details["expires_at"], int((self.token.created + timedelta(seconds=30)).timestamp()))

    def test_retry_is_persistent_and_does_not_target_new_login(self):
        from app.accounts.revocations import deliver
        old_version = authorization_version(self.user, self.token.key)
        self.gateway.side_effect = OSError("gateway down")
        self.token.delete()
        event = GatewayRevocation.objects.get()
        self.assertEqual(event.version, old_version)
        self.assertEqual(event.attempts, 1)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.token = Token.objects.create(user=self.user)
        self.assertNotEqual(authorization_version(self.user, self.token.key), old_version)
        self.gateway.reset_mock()
        deliver(event.pk)
        self.gateway.assert_not_called()  # retry delay / worker claim respected
        GatewayRevocation.objects.filter(pk=event.pk).update(next_attempt_at=timezone.now())
        self.gateway.side_effect = None
        call_command("retry_gateway_revocations", once=True)
        self.assertFalse(GatewayRevocation.objects.exists())
        self.assertEqual(self.gateway.call_args.kwargs["json"]["version"], old_version)

    def test_policy_change_revoke_and_revert_never_restore_old_grant(self):
        grant = self.grant()
        first_version = self.user.authorization_version
        self.user.model_limit = ["restricted"]
        self.user.save(update_fields=["model_limit"])
        self.assertFalse(authorization_is_active(grant, self.user.username))
        self.assertNotEqual(self.user.authorization_version, first_version)
        self.user.model_limit = []
        self.user.save(update_fields=["model_limit"])
        self.assertFalse(authorization_is_active(grant, self.user.username))
        self.assertTrue(authorization_is_active(self.grant(), self.user.username))
        self.assertEqual(self.gateway.call_count, 2)

    def test_each_permission_change_emits_revocation(self):
        changes = {"gptcar_list": [2], "model_limit": ["m"], "isolated_session": False,
                   "force_chat_mode": False, "daily_quota": 2, "monthly_quota": 4,
                   "is_staff": True, "is_superuser": True, "password": "reset-hash",
                   "expired_date": timezone.localdate() + timedelta(days=1), "is_active": False}
        for field, value in changes.items():
            before = self.gateway.call_count
            setattr(self.user, field, value)
            self.user.save(update_fields=[field])
            self.assertEqual(self.gateway.call_count, before + 1, field)

    def test_rollback_does_not_revoke_or_enqueue(self):
        grant = self.grant()
        try:
            with transaction.atomic():
                self.user.is_active = False
                self.user.save(update_fields=["is_active"])
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertTrue(authorization_is_active(grant, self.user.username))
        self.assertFalse(GatewayRevocation.objects.exists())
        self.gateway.assert_not_called()

    def test_delete_user_keeps_failed_revocation(self):
        self.gateway.side_effect = OSError("gateway down")
        self.user.delete()
        self.assertEqual(GatewayRevocation.objects.get().subject, "lease-user")

    def test_free_visitor_and_shared_user_revocations_are_distinct(self):
        free = User.objects.create_user(username=FREE_ACCOUNT_USERNAME)
        token = Token.objects.create(user=free)
        visitor = VisitorSession.objects.create(user=free, sid="a" * 32, expires_at=timezone.now() + timedelta(hours=1))
        visitor.delete()
        event = self.gateway.call_args.kwargs["json"]
        self.assertEqual(event["subject"], FREE_ACCOUNT_USERNAME + ":" + "a" * 32)
        self.assertFalse(event["include_visitors"])
        token.delete()
        self.assertTrue(self.gateway.call_args.kwargs["json"]["include_visitors"])

    def test_admin_revoke_confirms_delivery_in_real_transaction(self):
        revoke_user_sessions(self.user, require_gateway=True)
        self.assertFalse(GatewayRevocation.objects.exists())
        self.gateway.assert_called_once()


@override_settings(ALLOWED_HOSTS=["testserver"], CSRF_TRUSTED_ORIGINS=["https://testserver"],
                   GATEWAY_ADMIN_SECRET="internal-test-secret")
class LoginSecurityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="login-test", password="Strong-password-123!")
        self.client = APIClient(enforce_csrf_checks=True, HTTP_USER_AGENT="login-test")
        self.turnstile = patch("app.accounts.views.login.TURNSTILE_ENABLED", False)
        self.turnstile.start()
        self.addCleanup(self.turnstile.stop)

    def csrf(self, client=None):
        return (client or self.client).get("/0x/user/version-cfg").data["csrf_token"]

    def post(self, path, data=None, client=None, csrf=None, **headers):
        client = client or self.client
        return client.post(path, data or {}, format="json",
                           HTTP_X_CSRFTOKEN=csrf or self.csrf(client), **headers)

    def prepare(self, client=None, free=False):
        return self.post("/0x/user/login-free" if free else "/0x/user/login", {
            "username": self.user.username, "password": "Strong-password-123!",
        }, client=client)

    def login(self, client=None, free=False):
        prepared = self.prepare(client, free)
        self.assertEqual(prepared.status_code, 200, prepared.data)
        return self.post("/0x/user/login-confirm", {"login_ticket": prepared.data["login_ticket"]}, client=client)

    def grant(self, client=None, user=None):
        client, user = client or self.client, user or self.user
        request = SimpleNamespace(user=user, auth=Token.objects.get(user=user),
                                  COOKIES={key: value.value for key, value in client.cookies.items()})
        return gateway_authorization(request), get_request_subject(request)

    def test_all_public_login_posts_require_csrf(self):
        for path in ("login", "register", "login-free", "login-confirm", "logout"):
            response = self.client.post("/0x/user/" + path, {}, format="json")
            self.assertEqual(response.status_code, 403, path)

    def test_login_rejects_cross_origin_form_even_with_csrf_token(self):
        csrf = self.csrf()
        response = self.client.post("/0x/user/login", {
            "username": self.user.username, "password": "Strong-password-123!",
            "csrfmiddlewaretoken": csrf,
        }, HTTP_ORIGIN="https://attacker.example")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_prepare_does_not_issue_session_and_confirm_is_single_use(self):
        prepared = self.prepare()
        self.assertEqual(prepared.status_code, 200)
        self.assertNotIn(AUTH_COOKIE_NAME, prepared.cookies)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        ticket = prepared.data["login_ticket"]
        confirmed = self.post("/0x/user/login-confirm", {"login_ticket": ticket})
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertTrue(confirmed.cookies[AUTH_COOKIE_NAME]["httponly"])
        replay = self.post("/0x/user/login-confirm", {"login_ticket": ticket})
        self.assertEqual(replay.status_code, 400)

    def test_confirmation_is_bound_to_browser_csrf_secret(self):
        prepared = self.prepare()
        other = APIClient(enforce_csrf_checks=True)
        result = self.post("/0x/user/login-confirm", {"login_ticket": prepared.data["login_ticket"]}, client=other)
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_expired_or_password_stale_confirmation_cannot_issue_session(self):
        prepared = self.prepare()
        PendingLogin.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        result = self.post("/0x/user/login-confirm", {"login_ticket": prepared.data["login_ticket"]})
        self.assertEqual(result.status_code, 400)
        prepared = self.prepare()
        self.user.set_password("Changed-password-123!")
        self.user.save()
        result = self.post("/0x/user/login-confirm", {"login_ticket": prepared.data["login_ticket"]})
        self.assertEqual(result.status_code, 400)
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    @patch("app.accounts.views.login.requests.post")
    def test_turnstile_failure_and_expiry_never_create_pending_login(self, siteverify):
        with patch("app.accounts.views.login.TURNSTILE_ENABLED", True):
            for result in (
                {"success": False, "error-codes": ["timeout-or-duplicate"]},
                {"success": "true", "action": "login", "challenge_ts": timezone.now().isoformat()},
                {"success": True, "action": "login", "challenge_ts": (timezone.now() - timedelta(seconds=301)).isoformat()},
            ):
                siteverify.return_value.json.return_value = result
                response = self.post("/0x/user/login", {
                    "username": self.user.username, "password": "Strong-password-123!", "turnstile_token": "test",
                })
                self.assertEqual(response.status_code, 400)
        self.assertFalse(PendingLogin.objects.exists())
        self.assertFalse(Token.objects.exists())

    @patch("app.accounts.views.login.req_gateway", side_effect=ValidationError("gateway down"))
    def test_logout_revokes_authority_even_when_gateway_cleanup_fails(self, _gateway):
        self.assertEqual(self.login().status_code, 200)
        grant, subject = self.grant()
        self.assertTrue(authorization_is_active(grant, subject))
        response = self.post("/0x/user/logout")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["gateway_cleanup_pending"])
        self.assertFalse(authorization_is_active(grant, subject))
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    @patch("app.accounts.views.req_gateway", side_effect=ValidationError("gateway down"))
    def test_password_change_revokes_old_gateway_authority(self, _gateway):
        self.login()
        grant, subject = self.grant()
        result = self.post("/0x/user/change-password", {
            "current_password": "Strong-password-123!", "new_password": "New-strong-password-987!",
        })
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(authorization_is_active(grant, subject))

    @patch("app.accounts.views.req_gateway", side_effect=ValidationError("gateway down"))
    def test_admin_revoke_fails_closed_and_cancels_pending_tickets(self, _gateway):
        self.login()
        grant, subject = self.grant()
        self.prepare()
        revoke_user_sessions(self.user)
        self.assertFalse(authorization_is_active(grant, subject))
        self.assertFalse(PendingLogin.objects.filter(user=self.user).exists())

    def test_authority_checks_expiry_deletion_and_subject(self):
        self.login()
        grant, subject = self.grant()
        self.assertFalse(authorization_is_active(grant, "another-user"))
        self.user.expired_date = timezone.localdate()
        self.user.save()
        self.assertFalse(authorization_is_active(grant, subject))
        self.user.delete()
        self.assertFalse(authorization_is_active(grant, subject))

    def test_policy_changes_reject_old_authority_without_relying_on_remote_cleanup(self):
        self.login()
        grant, subject = self.grant()
        User.objects.filter(pk=self.user.pk).update(model_limit=["restricted-model"])
        self.assertTrue(Token.objects.filter(user=self.user).exists())
        self.assertFalse(authorization_is_active(grant, subject))

    def test_internal_authority_endpoint_requires_service_secret(self):
        self.login()
        grant, subject = self.grant()
        data = {"authorization": grant, "subject": subject}
        denied = self.client.post("/0x/user/gateway-authorization", data, format="json")
        self.assertIn(denied.status_code, (401, 403))
        allowed = self.client.post("/0x/user/gateway-authorization", data, format="json",
                                   HTTP_AUTHORIZATION="Bearer internal-test-secret")
        self.assertEqual(allowed.status_code, 200)

    @patch("app.accounts.views.login.req_gateway", return_value={})
    def test_free_logout_blocks_replay_without_logging_out_other_visitor(self, _gateway):
        free = User.objects.create_user(username=FREE_ACCOUNT_USERNAME, password="Free-password-123!")
        other = APIClient(enforce_csrf_checks=True, HTTP_USER_AGENT="other-visitor")
        self.assertEqual(self.login(free=True).status_code, 200)
        self.assertEqual(self.login(other, free=True).status_code, 200)
        old_cookies = self.client.cookies.copy()
        grant, subject = self.grant(user=free)
        other_grant, other_subject = self.grant(other, free)
        self.assertNotEqual(subject, other_subject)
        self.assertEqual(self.post("/0x/user/logout").status_code, 200)
        self.assertFalse(authorization_is_active(grant, subject))
        self.assertTrue(authorization_is_active(other_grant, other_subject))
        self.client.cookies = old_cookies
        self.assertNotEqual(self.client.get("/0x/user/me").status_code, 200)
        self.assertEqual(VisitorSession.objects.count(), 1)

    def test_ip_throttle_uses_gateway_client_address(self):
        factory = APIRequestFactory()
        first = factory.post("/0x/user/login", HTTP_X_CHATGPT_MIRROR_CLIENT_IP="203.0.113.10")
        second = factory.post("/0x/user/login", HTTP_X_CHATGPT_MIRROR_CLIENT_IP="203.0.113.11")
        for _ in range(20):
            self.assertTrue(LoginIpRateThrottle().allow_request(first, None))
        self.assertFalse(LoginIpRateThrottle().allow_request(first, None))
        self.assertTrue(LoginIpRateThrottle().allow_request(second, None))
