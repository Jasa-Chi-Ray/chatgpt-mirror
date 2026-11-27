import time
from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from app.accounts.models import User
from app.chatgpt.models import AccountUsageSchedule, ChatgptAccount, ChatgptCar
from app.chatgpt.usage_monitor import normalize_usage, public_usage, run_next_check


@override_settings(SESSION_COOKIE_SECURE=False)
class AutomationLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="automation-user", password="fixture")
        self.other = User.objects.create_user(username="automation-other", password="fixture")
        self.admin = User.objects.create_user(username="automation-admin", password="fixture", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user, Token.objects.create(user=self.user))
        self.credentials = {"web_identity_id":"a"*64,"credential_version":1,"access_token":"fixture-access","session_token":"fixture-session", "access_token_valid":True,"session_token_valid":True,"user_info":{"email":"fixture@example.test","plan_type":"plus"}}
        self.preview = {"status":"ready","email":"fixture@example.test"}
    def account(self, **kw):
        return ChatgptAccount.objects.create(chatgpt_username="fixture@example.test",access_token="old",created_time=1,updated_time=1,**kw)
    def gateway(self, *a, **kw):
        action = kw["json"]["action"]
        return self.preview if action=="preview" else {"status":"connected","credentials":self.credentials,"connection":{"id":"a"*64}} if action=="complete" else {"message":"done"}
    def post(self, action, **kw):
        return self.client.post("/0x/chatgpt/web-login", {"action":action,**kw},format="json")
    def test_duplicate_requires_explicit_signed_confirmation_and_retains_old_until_confirmed(self):
        account=self.account(automation_owner=self.user)
        with patch("app.chatgpt.views.web_login.req_gateway",side_effect=self.gateway):
            first=self.post("complete",flow="b"*64)
            self.assertEqual(first.data["status"],"overwrite_required")
            account.refresh_from_db();self.assertEqual(account.access_token,"old")
            second=self.post("complete",flow="b"*64,overwrite_token=first.data["overwrite_token"])
        self.assertEqual(second.data["status"],"connected")
        account.refresh_from_db();self.assertEqual(account.access_token,"fixture-access")
        self.assertEqual(ChatgptAccount.objects.count(),1)
        self.assertNotIn("fixture-access",str(second.data))
    def test_stale_confirmation_is_prompted_again(self):
        account=self.account(automation_owner=self.user)
        with patch("app.chatgpt.views.web_login.req_gateway",side_effect=self.gateway):
            first=self.post("complete",flow="b"*64)
            account.updated_time=2;account.save(update_fields=["updated_time"])
            second=self.post("complete",flow="b"*64,overwrite_token=first.data["overwrite_token"])
        self.assertEqual(second.data["status"],"overwrite_required")
    def test_personal_import_cannot_take_over_another_users_or_shared_account(self):
        self.account(automation_owner=self.other)
        with patch("app.chatgpt.views.web_login.req_gateway",side_effect=self.gateway) as gateway:
            self.assertEqual(self.post("complete",flow="b"*64).status_code,403)
            self.assertEqual(gateway.call_count,1)
    def test_disconnect_default_retains_record_but_erases_all_credentials(self):
        account=self.account(automation_owner=self.user,web_identity_id="a"*64,session_token="secret",refresh_token="secret",extra_cookies=[{"name":"cookie","value":"secret"}])
        with patch("app.chatgpt.views.web_login.req_gateway",side_effect=self.gateway):
            self.assertEqual(self.post("disconnect",id="a"*64).status_code,200)
        account.refresh_from_db()
        self.assertEqual(account.access_token,"");self.assertIsNone(account.session_token)
        self.assertIsNone(account.refresh_token);self.assertEqual(account.extra_cookies,[])
        self.assertIsNone(account.web_identity_id)
    def test_disconnect_then_account_delete_is_idempotent_and_prunes_car_references(self):
        account=self.account(automation_owner=self.user,web_identity_id="a"*64)
        car=ChatgptCar.objects.create(car_name="fixture-car",gpt_account_list=[account.pk],created_time=1,updated_time=1)
        with patch("app.chatgpt.views.web_login.req_gateway",side_effect=self.gateway):self.post("disconnect",id="a"*64)
        self.client.force_authenticate(self.admin,Token.objects.create(user=self.admin))
        with patch("app.chatgpt.account_lifecycle.req_gateway") as gateway:
            for _ in range(2):self.assertEqual(self.client.delete("/0x/chatgpt/",{"chatgpt_username":account.chatgpt_username},format="json").status_code,200)
            gateway.assert_not_called()
        car.refresh_from_db();self.assertEqual(car.gpt_account_list,[])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
    def test_optional_delete_and_private_listing_scope(self):
        account=self.account(automation_owner=self.user,web_identity_id="a"*64)
        self.assertEqual(list(ChatgptAccount.get_for_user(self.other)),[])
        self.assertEqual(list(ChatgptAccount.get_for_user(self.user)),[account])
        with patch("app.chatgpt.account_lifecycle.req_gateway",return_value={}) as gateway:
            self.assertEqual(self.post("disconnect",id="a"*64,delete_upstream=True).status_code,200)
            self.assertEqual(gateway.call_args.kwargs["json"]["id"],"a"*64)
        self.assertFalse(ChatgptAccount.objects.exists())

    def test_user_account_list_hides_login_count_and_detailed_usage(self):
        self.account(automation_owner=self.user, login_count=19, usage_snapshot={"state":"busy","used_percent":70,"remaining_percent":30,"models":[{"model":"upstream-model"}]},usage_checked_at=int(time.time()))
        response=self.client.get("/0x/user/chatgpt-list")
        self.assertEqual(response.status_code,200)
        item=response.data["results"][0]
        self.assertNotIn("login_count",item)
        self.assertEqual(item["usage"]["remaining_percent"],30)
        self.assertNotIn("models",item["usage"])

    def test_deleting_owner_cannot_turn_a_private_account_into_a_shared_account(self):
        account=self.account(automation_owner=self.user)
        self.user.delete()
        self.assertFalse(ChatgptAccount.objects.filter(pk=account.pk).exists())


class UsageScheduleTests(TestCase):
    def test_sanitized_upstream_percent_models_and_no_invented_quota(self):
        result=normalize_usage({"email":"private", "rate_limit":{"primary_window":{"used_percent":73,"reset_at":123}},"model_usage":{"gpt-test":{"available":False}}})
        self.assertEqual(result["state"],"busy");self.assertEqual(result["remaining_percent"],27)
        self.assertNotIn("private",str(result));self.assertFalse(result["models"][0]["available"])
        self.assertIsNone(normalize_usage({})["used_percent"])
    def test_hourly_checks_are_staggered_globally_and_public_snapshot_has_no_models(self):
        now=int(time.time())
        first=ChatgptAccount.objects.create(chatgpt_username="first@example.test",access_token="first",created_time=1,updated_time=1,auth_status=True,access_token_valid=True)
        ChatgptAccount.objects.create(chatgpt_username="second@example.test",access_token="second",created_time=1,updated_time=1,auth_status=True,access_token_valid=True)
        with patch("app.chatgpt.usage_monitor.req_gateway",return_value={"rate_limit":{"primary_window":{"used_percent":20}}}) as gateway:
            self.assertTrue(run_next_check(now));self.assertFalse(run_next_check(now));self.assertEqual(gateway.call_count,1)
        first.refresh_from_db();self.assertEqual(first.usage_next_check_at,now+3600)
        schedule=AccountUsageSchedule.objects.get();self.assertGreaterEqual(schedule.next_dispatch_at-now,30);self.assertLessEqual(schedule.next_dispatch_at-now,82)
        self.assertNotIn("models",public_usage(first));self.assertIn("models",public_usage(first,True))
