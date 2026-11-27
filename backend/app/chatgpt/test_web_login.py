from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from app.accounts.models import User
from app.chatgpt.models import ChatgptAccount


@override_settings(SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class WebLoginTests(TestCase):
    url = "/0x/chatgpt/web-login"

    def setUp(self):
        self.user = User.objects.create_user(username="connect-member", password="test-password")
        self.admin = User.objects.create_user(username="connect-admin", password="test-password", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user, Token.objects.create(user=self.user))

    def post(self, action, **kwargs):
        return self.client.post(self.url, {"action": action, **kwargs}, format="json")

    def credentials(self):
        return {"web_identity_id": "a" * 64, "credential_version": 1, "access_token": "private-access", "session_token": "private-session",
                "extra_cookies": [{"name": "private-cookie", "value": "private-value"}],
                "access_token_valid": True, "session_token_valid": True,
                "user_info": {"email": "upstream@example.test", "plan_type": "plus"}}

    def test_requires_local_login_and_admin_for_pool(self):
        self.client.force_authenticate(user=None, token=None)
        self.assertIn(self.post("start").status_code, (401, 403))
        self.client.force_authenticate(self.user, Token.objects.get(user=self.user))
        with patch("app.chatgpt.views.web_login.req_gateway") as gateway:
            self.assertEqual(self.post("start", pool=True).status_code, 403)
            self.assertEqual(self.post("start", proxy_node_id=2).status_code, 403)
            gateway.assert_not_called()

    def test_owner_is_derived_from_authenticated_user_and_binding_is_http_only(self):
        with patch("app.chatgpt.views.web_login.req_gateway", return_value={"authorize_url": "/__upstream-login/start?ticket=opaque", "expires_in": 1200}) as gateway:
            response = self.post("start", owner="someone-else", authorization="forged")
        self.assertEqual(response.status_code, 200)
        sent = gateway.call_args.kwargs["json"]
        self.assertEqual(sent["owner"], self.user.username)
        self.assertNotEqual(sent["authorization"], "forged")
        self.assertEqual(len(sent["binding"]), 64)
        self.assertTrue(response.cookies["mirror_web_login_binding"]["httponly"])
        self.assertNotIn("binding", response.data)
        self.assertTrue(sent["policy"]["isolated_session"])

    def test_embedded_start_and_single_flow_cancellation_are_forwarded_without_client_owner_fields(self):
        with patch("app.chatgpt.views.web_login.req_gateway", return_value={"authorize_url": "/__upstream-login/start?ticket=" + "a"*64}) as gateway:
            self.assertEqual(self.post("start", embedded=True).status_code, 200)
            payload = gateway.call_args.kwargs["json"]
            self.assertTrue(payload["policy"]["_embedded"])
            self.assertEqual(payload["owner"], self.user.username)
            self.assertEqual(self.post("cancel", flow="a"*64).status_code, 200)
            self.assertEqual(gateway.call_args.kwargs["json"]["flow_token"], "a"*64)

    def test_private_connection_never_imports_into_shared_pool_or_returns_credentials(self):
        self.client.cookies["mirror_web_login"] = "b" * 64
        self.client.cookies["mirror_web_login_binding"] = "c" * 64
        result = {"status": "connected", "connection": {"id": "a" * 64, "label": "upstream@example.test"}, "credentials": self.credentials()}
        with patch("app.chatgpt.views.web_login.req_gateway", side_effect=lambda *a, **kw: {"status":"ready", "email":self.credentials()["user_info"]["email"]} if kw["json"]["action"] == "preview" else result) as gateway:
            response = self.post("complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChatgptAccount.objects.get().automation_owner_id, self.user.pk)
        self.assertNotIn("credentials", response.data)
        self.assertNotIn("private-access", response.content.decode())
        self.assertEqual(gateway.call_args.kwargs["json"]["flow_token"], "b" * 64)

    def test_pool_completion_imports_credentials_server_side_only(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        result = {"status": "connected", "connection": {"id": "a" * 64}, "credentials": self.credentials()}
        with patch("app.chatgpt.views.web_login.req_gateway", side_effect=lambda *a, **kw: {"status":"ready", "email":self.credentials()["user_info"]["email"]} if kw["json"]["action"] == "preview" else result):
            response = self.post("complete", pool=True)
        self.assertEqual(response.status_code, 200)
        account = ChatgptAccount.objects.get()
        self.assertEqual(account.web_identity_id, "a" * 64)
        self.assertEqual(account.access_token, "private-access")
        self.assertNotIn("private-access", response.content.decode())

    def test_sync_requires_service_secret_and_cannot_redirect_credentials_to_another_account(self):
        client = APIClient()
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                               web_identity_id="a" * 64, created_time=1, updated_time=1)
        credentials = self.credentials()
        self.assertEqual(client.post(self.url + "/sync", credentials, format="json").status_code, 401)
        credentials["user_info"]["email"] = "other@example.test"
        response = client.post(self.url + "/sync", credentials, format="json", HTTP_AUTHORIZATION="Bearer " + settings.GATEWAY_ADMIN_SECRET)
        self.assertEqual(response.status_code, 400)
        account.refresh_from_db()
        self.assertEqual(account.access_token, "old")
        credentials["user_info"]["email"] = account.chatgpt_username
        self.assertEqual(client.post(self.url + "/sync", credentials, format="json", HTTP_AUTHORIZATION="Bearer " + settings.GATEWAY_ADMIN_SECRET).status_code, 200)
        account.refresh_from_db()
        self.assertEqual(account.access_token, "private-access")

    def test_cookie_authentication_requires_csrf_for_start(self):
        client = APIClient(enforce_csrf_checks=True)
        client.cookies["mirror_api_session"] = Token.objects.get(user=self.user).key
        with patch("app.chatgpt.views.web_login.req_gateway") as gateway:
            self.assertEqual(client.post(self.url, {"action": "start"}, format="json").status_code, 403)
            gateway.assert_not_called()

    def test_automatic_sync_preserves_edits_and_rejects_late_versions_and_detached_connections(self):
        from app.chatgpt.views.web_login import apply_web_credentials
        from rest_framework.exceptions import ValidationError
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                               web_identity_id="a" * 64, created_time=1, updated_time=123, remark="keep-this")
        stale = ChatgptAccount.objects.get(pk=account.pk)
        latest = {**self.credentials(), "credential_version": 3, "access_token": "newest"}
        apply_web_credentials(account, latest)
        apply_web_credentials(stale, self.credentials())
        account.refresh_from_db()
        self.assertEqual(account.access_token, "newest")
        self.assertEqual(account.web_identity_version, 3)
        self.assertEqual(account.updated_time, 123)
        self.assertEqual(account.remark, "keep-this")
        ChatgptAccount.objects.filter(pk=account.pk).update(web_identity_id=None)
        with self.assertRaises(ValidationError):
            apply_web_credentials(stale, latest)
        account.refresh_from_db()
        self.assertIsNone(account.web_identity_id)

    def test_owners_service_matches_user_id_and_username_without_exposing_account_data(self):
        client = APIClient()
        owner = f"{self.user.pk}:{self.user.username}"
        wrong = f"{self.user.pk + 100}:{self.user.username}"
        self.assertEqual(client.post(self.url + "/owners", {"owners": [owner]}, format="json").status_code, 401)
        response = client.post(self.url + "/owners", {"owners": [owner, wrong]}, format="json",
                               HTTP_AUTHORIZATION="Bearer " + settings.GATEWAY_ADMIN_SECRET)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"present": [owner]})
        self.assertEqual(client.post(self.url + "/owners", {"owners": ["pool"]}, format="json",
                                     HTTP_AUTHORIZATION="Bearer " + settings.GATEWAY_ADMIN_SECRET).status_code, 400)

    def test_pool_edit_and_delete_update_only_the_matching_rust_connection(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                               web_identity_id="a" * 64, created_time=1, updated_time=1)
        with patch("app.chatgpt.views.chatgpt.req_gateway", return_value=self.credentials()) as gateway, patch("app.chatgpt.account_lifecycle.req_gateway", return_value={}) as cleanup:
            response = self.client.put("/0x/chatgpt/", {"chatgpt_username": account.chatgpt_username, "remark": "edited", "proxy_node_id": 7}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(gateway.call_args.kwargs["json"]["action"], "configure-pool")
            self.assertEqual(gateway.call_args.kwargs["json"]["proxy_node_id"], 7)
            account.refresh_from_db()
            self.assertEqual(account.proxy_node_id, 7)
            response = self.client.delete("/0x/chatgpt/", {"chatgpt_username": account.chatgpt_username}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(cleanup.call_args.kwargs["json"]["action"], "disconnect")
            self.assertTrue(cleanup.call_args.kwargs["json"]["pool"])
            self.assertFalse(ChatgptAccount.objects.filter(pk=account.pk).exists())

    def test_existing_refresh_button_uses_managed_session_without_refresh_token(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                               web_identity_id="a" * 64, created_time=1, updated_time=1)
        result = {"status": "renewed", "credentials": self.credentials()}
        with patch("app.chatgpt.views.chatgpt.req_gateway", side_effect=lambda *a, **kw: {"status":"ready", "email":self.credentials()["user_info"]["email"]} if kw["json"]["action"] == "preview" else result) as gateway:
            response = self.client.post("/0x/chatgpt/refresh-token", {"id": account.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(gateway.call_args.args[1], "/api/web-login")
        self.assertEqual(gateway.call_args.kwargs["json"]["action"], "renew-pool")
        self.assertEqual(response.data["status"], "renewed")
        account.refresh_from_db()
        self.assertEqual(account.access_token, "private-access")
        self.assertEqual(account.web_identity_version, 1)

    def test_failed_forced_renewal_keeps_live_tokens_and_requests_interactive_login(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", access_token="working-access", session_token="working-session", web_identity_id="a"*64, created_time=1, updated_time=1)
        with patch("app.chatgpt.views.chatgpt.req_gateway", return_value={"status":"reauth_required"}):
            response = self.client.post("/0x/chatgpt/refresh-token", {"id":account.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "reauth_required")
        self.assertNotIn("result", response.data)
        account.refresh_from_db()
        self.assertEqual(account.access_token, "working-access")
        self.assertEqual(account.session_token, "working-session")

    def test_manual_account_requests_native_login_for_both_new_tokens(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", access_token="working", created_time=1, updated_time=1)
        with patch("app.chatgpt.views.chatgpt.req_gateway") as gateway:
            response = self.client.post("/0x/chatgpt/refresh-token", {"id":account.pk, "force_web":True}, format="json")
        self.assertEqual(response.data["status"], "manual_required")
        gateway.assert_not_called()

    def test_reconnect_start_targets_the_selected_admin_account(self):
        self.client.force_authenticate(self.admin, Token.objects.create(user=self.admin))
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", access_token="working", created_time=1, updated_time=1)
        with patch("app.chatgpt.views.web_login.req_gateway", return_value={"authorize_url":"/local"}) as gateway:
            response = self.post("start", pool=True, embedded=True, account_id=account.pk)
        self.assertEqual(response.status_code, 200)
        policy = gateway.call_args.kwargs["json"]["policy"]
        self.assertEqual(policy["_expected_email"], account.chatgpt_username)
        self.assertEqual(policy["_pool_target_account_id"], account.pk)
        self.assertTrue(policy["_force_renewal"])
        with patch("app.chatgpt.views.web_login.req_gateway") as gateway:
            self.assertEqual(self.post("start", pool=True, account_id=account.pk, id="b"*64).status_code, 400)
            gateway.assert_not_called()
        self.client.force_authenticate(self.user, Token.objects.get(user=self.user))
        with patch("app.chatgpt.views.web_login.req_gateway") as gateway:
            self.assertEqual(self.post("start", account_id=account.pk).status_code, 403)
            gateway.assert_not_called()

    def test_manual_import_cannot_be_silently_overwritten_by_a_managed_connection(self):
        from app.chatgpt.views.chatgpt import ChatGPTAccountView
        from rest_framework.exceptions import ValidationError
        ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                     web_identity_id="a" * 64, created_time=1, updated_time=1)
        with self.assertRaises(ValidationError):
            ChatGPTAccountView.ensure_manual_credentials(self.credentials())

    def test_private_connection_without_a_configured_model_policy_can_use_upstream_models(self):
        self.assertTrue(self.user.model_isolation)
        self.user.model_limit = ["blocked-model"]
        self.user.daily_quota = 12
        self.user.save()
        with patch("app.chatgpt.views.web_login.req_gateway", return_value={"login_url": "/api/not-login?user_gateway_token=fixture"}) as gateway:
            response = self.post("activate", id="a" * 64)
        self.assertEqual(response.status_code, 200)
        policy = gateway.call_args.kwargs["json"]["policy"]
        self.assertFalse(policy["model_isolation"])
        self.assertEqual(policy["model_allowed_ids"], [])
        self.assertEqual(policy["limits"], ["blocked-model"])
        self.assertEqual(policy["daily_quota"], 12)
        self.assertTrue(policy["isolated_session"])

    def test_private_connection_uses_existing_model_policy_from_server_verified_identity(self):
        account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.test", plan_type="plus", access_token="old",
                                               created_time=1, updated_time=1)
        self.user.model_policies = [{"account_id": account.pk, "models": [{"id": "allowed-model", "hour_limit": 8}]}]
        self.user.save()
        connection = {"id": "a" * 64, "email": account.chatgpt_username}
        with patch("app.chatgpt.views.web_login.req_gateway", side_effect=[{"connections": [connection]}, {"login_url": "/api/not-login?user_gateway_token=fixture"}]) as gateway:
            response = self.post("activate", id=connection["id"], email="forged@example.test", model_isolation=False)
        self.assertEqual(response.status_code, 200)
        policy = gateway.call_args.kwargs["json"]["policy"]
        self.assertTrue(policy["model_isolation"])
        self.assertEqual(policy["model_allowed_ids"], ["allowed-model"])
        self.assertEqual(policy["model_rate_limits"]["allowed-model"]["hour_limit"], 8)
        with patch("app.chatgpt.views.web_login.req_gateway", return_value={"connections": []}) as gateway:
            self.assertEqual(self.post("activate", id="b" * 64).status_code, 400)
            self.assertEqual(gateway.call_count, 1)
