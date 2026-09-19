from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.accounts.models import User
from app.chatgpt.health_mail import MailDeliveryError, send_notification, test_imap
from app.chatgpt.health_monitor import CONFIRM_SECONDS, due_checks, run_check
from app.chatgpt.models import AccountHealthSettings, AccountHealthState, ChatgptAccount


class HealthSettingsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(username="health-admin", is_superuser=True, is_staff=True)
        self.client.force_authenticate(self.admin)
        self.config = AccountHealthSettings.objects.create(
            smtp_host="smtp.example.com", smtp_username="sender@example.com", smtp_password="secret-smtp",
            imap_host="imap.example.com", imap_username="sender@example.com", imap_password="secret-imap",
            recipient="ops@example.com",
        )
        self.url = "/0x/chatgpt/health-settings"

    def payload(self, **changes):
        data = self.client.get(self.url).json()
        data.update(changes)
        return data

    def test_secrets_encrypted_and_never_returned(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("smtp_password", response.data)
        self.assertNotIn("imap_password", response.data)
        self.assertTrue(response.data["smtp_configured"])
        with connection.cursor() as cursor:
            cursor.execute("SELECT smtp_password, imap_password FROM chatgpt_accounthealthsettings WHERE id=1")
            for value in cursor.fetchone():
                self.assertTrue(value.startswith("enc:v1:"))
                self.assertNotIn("secret", value)

    def test_blank_keeps_secret_and_new_value_replaces(self):
        response = self.client.put(self.url, self.payload(smtp_password="", imap_password="new-imap"), format="json")
        self.assertEqual(response.status_code, 200)
        self.config.refresh_from_db()
        self.assertEqual(self.config.smtp_password, "secret-smtp")
        self.assertEqual(self.config.imap_password, "new-imap")
        self.assertNotIn("new-imap", str(response.data))

    def test_minimum_interval_and_tls_enforced(self):
        for changes in ({"interval_minutes": 1}, {"smtp_security": "none"}, {"smtp_port": 0}):
            self.assertEqual(self.client.put(self.url, self.payload(**changes), format="json").status_code, 400)

    def test_changed_server_cannot_reuse_retained_secret(self):
        for changes in ({"smtp_host": "other.example.com"}, {"imap_username": "other@example.com"}, {"smtp_port": 587}):
            self.assertEqual(self.client.put(self.url, self.payload(**changes), format="json").status_code, 400)
        self.assertEqual(self.client.put(self.url, self.payload(smtp_host="other.example.com", smtp_password="replacement"), format="json").status_code, 200)

    @patch("app.chatgpt.views.health.send_notification")
    def test_recipient_change_test_can_be_skipped_and_same_address_never_sends(self, send):
        self.assertEqual(self.client.put(self.url, self.payload(test_on_recipient_change=True), format="json").status_code, 200)
        send.assert_not_called()
        self.assertEqual(self.client.put(self.url, self.payload(recipient="OPS@example.com", test_on_recipient_change=True), format="json").status_code, 200)
        send.assert_not_called()
        self.assertEqual(self.client.put(self.url, self.payload(recipient="new@example.com", test_on_recipient_change=False), format="json").status_code, 200)
        send.assert_not_called()
        self.assertEqual(self.client.put(self.url, self.payload(recipient="final@example.com", test_on_recipient_change=True), format="json").status_code, 200)
        self.assertEqual(send.call_args.args[0].recipient, "final@example.com")
        self.assertEqual(send.call_count, 1)

    @patch("app.chatgpt.views.health.send_notification", side_effect=MailDeliveryError("SMTP 发送失败"))
    def test_failed_recipient_test_does_not_save(self, send):
        response = self.client.put(self.url, self.payload(recipient="new@example.com", test_on_recipient_change=True), format="json")
        self.assertEqual(response.status_code, 400)
        self.config.refresh_from_db()
        self.assertEqual(self.config.recipient, "ops@example.com")

    def test_requires_root_admin_for_all_operations(self):
        for admin in (False, True):
            user = User.objects.create_user(username=f"staff-{admin}", is_staff=admin)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.put(self.url, {}, format="json").status_code, 403)
            self.assertEqual(self.client.post(self.url, {"action": "test_mail"}, format="json").status_code, 403)

    def test_stale_revision_rejected(self):
        data = self.payload()
        self.assertEqual(self.client.put(self.url, data, format="json").status_code, 200)
        self.assertEqual(self.client.put(self.url, data, format="json").status_code, 400)

    def test_cannot_enable_without_mail_credentials(self):
        AccountHealthSettings.objects.filter(pk=1).update(smtp_password="")
        self.assertEqual(self.client.put(self.url, self.payload(enabled=True), format="json").status_code, 400)


class HealthMonitorTests(TestCase):
    def setUp(self):
        self.config = AccountHealthSettings.objects.create(enabled=True, interval_minutes=2, recipient="ops@example.com")
        self.account = ChatgptAccount.objects.create(chatgpt_username="upstream@example.com", plan_type="pro",
                                                   access_token="private-access-token", created_time=1, updated_time=1)
        self.gateway = patch("app.chatgpt.health_monitor.req_gateway", return_value={"access_token_valid": False, "session_token_valid": False}).start()
        self.send = patch("app.chatgpt.health_monitor.send_notification").start()
        self.addCleanup(patch.stopall)
        self.now = timezone.now()

    def tick(self, offset=0):
        with patch("app.chatgpt.health_monitor.timezone.now", return_value=self.now + timedelta(seconds=offset)):
            for job in due_checks():
                run_check(*job)

    def test_first_failure_waits_18_seconds_then_notifies_once(self):
        self.tick()
        self.send.assert_not_called()
        state = AccountHealthState.objects.get()
        self.assertEqual(state.next_check_at, self.now + timedelta(seconds=CONFIRM_SECONDS))
        self.tick(17)
        self.assertEqual(self.gateway.call_count, 1)
        self.tick(18)
        self.assertEqual(self.send.call_count, 1)
        self.tick(140)
        self.assertEqual(self.send.call_count, 1)
        self.assertNotIn("private-access-token", str(self.send.call_args))
        self.account.refresh_from_db()
        self.assertTrue(self.account.auth_status)
        self.assertEqual(self.account.access_token, "private-access-token")

    def test_transient_failure_does_not_notify(self):
        self.tick()
        self.gateway.return_value = {"access_token_valid": True, "session_token_valid": False}
        self.tick(18)
        self.send.assert_not_called()
        self.assertIsNone(AccountHealthState.objects.get().first_failure_at)

    def test_recovery_rearms_notification(self):
        self.tick()
        self.tick(18)
        self.gateway.return_value = {"access_token_valid": False, "session_token_valid": True}
        self.tick(140)
        self.gateway.return_value = {"access_token_valid": False, "session_token_valid": False}
        self.tick(261)
        self.tick(279)
        self.assertEqual(self.send.call_count, 2)

    def test_mail_failure_persists_retry_and_rechecks_before_resend(self):
        self.send.side_effect = MailDeliveryError("SMTP 发送失败")
        self.tick()
        self.tick(18)
        self.assertFalse(AccountHealthState.objects.get().notified)
        self.config.refresh_from_db()
        self.assertEqual(self.config.last_mail_error, "SMTP 发送失败")
        self.tick(137)
        self.assertEqual(self.send.call_count, 1)
        self.send.side_effect = None
        self.tick(138)
        self.assertEqual(self.send.call_count, 2)
        self.assertTrue(AccountHealthState.objects.get().notified)

    def test_disabled_or_changed_configuration_skips_stale_jobs(self):
        job = due_checks()[0]
        AccountHealthSettings.objects.filter(pk=1).update(revision=1)
        run_check(*job)
        self.gateway.assert_not_called()
        AccountHealthSettings.objects.filter(pk=1).update(enabled=False)
        self.assertEqual(due_checks(), [])

    def test_parallel_workers_do_not_claim_same_account_and_expired_lease_recovers(self):
        self.assertEqual(len(due_checks()), 1)
        self.assertEqual(due_checks(), [])
        AccountHealthState.objects.update(lease_until=self.now - timedelta(seconds=1))
        self.assertEqual(len(due_checks()), 1)

    def test_reserved_worker_preserves_lease_until_confirmation(self):
        job = due_checks()[0]
        self.assertEqual(run_check(*job, reserve_confirmation=True), 18)
        self.assertEqual(due_checks(), [])
        with patch("app.chatgpt.health_monitor.timezone.now", return_value=timezone.now() + timedelta(seconds=19)):
            run_check(*job)
        self.assertTrue(AccountHealthState.objects.get().notified)
        self.assertEqual(AccountHealthState.objects.get().lease_token, "")

    def test_gateway_error_is_sanitized_and_needs_confirmation(self):
        self.gateway.side_effect = RuntimeError("private-access-token")
        self.tick()
        self.send.assert_not_called()
        self.tick(18)
        self.assertEqual(self.send.call_count, 1)
        self.assertNotIn("private-access-token", self.send.call_args.args[2])

    def test_inflight_account_edit_drops_stale_result(self):
        def edit(*args, **kwargs):
            ChatgptAccount.objects.filter(pk=self.account.pk).update(updated_time=2)
            return {"access_token_valid": False, "session_token_valid": False}
        self.gateway.side_effect = edit
        self.tick()
        self.assertIsNone(AccountHealthState.objects.get().first_failure_at)
        self.send.assert_not_called()


class MailTransportTests(TestCase):
    def setUp(self):
        self.config = AccountHealthSettings(smtp_host="smtp.example.com", smtp_username="sender@example.com",
                                           smtp_password="secret", recipient="ops@example.com", smtp_security="starttls", smtp_port=587,
                                           imap_host="imap.example.com", imap_username="sender@example.com", imap_password="secret")

    @patch("app.chatgpt.health_mail.smtplib.SMTP")
    def test_starttls_precedes_login_and_recipient_is_explicit(self, smtp):
        # SMTP.__enter__ returns self in production.
        smtp.return_value.__enter__.return_value = smtp.return_value
        client = smtp.return_value
        client.send_message.return_value = {}
        send_notification(self.config, "test", "body")
        names = [call[0] for call in client.mock_calls]
        self.assertLess(names.index("starttls"), names.index("login"))
        message = client.send_message.call_args.args[0]
        self.assertEqual(message["To"], "ops@example.com")
        self.assertEqual(message.get_content_type(), "multipart/alternative")
        self.assertEqual(message.get_body(preferencelist=("plain",)).get_content().strip(), "body")
        self.assertIn("邮件服务测试", message.get_body(preferencelist=("html",)).get_content())

    @patch("app.chatgpt.health_mail.smtplib.SMTP_SSL")
    def test_html_alert_escapes_dynamic_content_and_keeps_plaintext(self, smtp):
        self.config.smtp_security = "ssl"
        smtp.return_value.send_message.return_value = {}
        send_notification(self.config, "账号状态异常 · example@example.com", "账号：example@example.com\n检测结果：异常",
                          details=[("异常账号", "example@example.com"), ("检测结果", '<img src="x" onerror="bad()">')])
        message = smtp.return_value.send_message.call_args.args[0]
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn("账号状态异常", html)
        self.assertIn("example@example.com", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn(self.config.smtp_password, html)
        self.assertIn("检测结果：异常", message.get_body(preferencelist=("plain",)).get_content())

    @patch("app.chatgpt.health_mail.smtplib.SMTP", side_effect=RuntimeError("secret upstream body"))
    def test_errors_never_expose_provider_body(self, smtp):
        with self.assertRaises(MailDeliveryError) as caught:
            send_notification(self.config, "test", "body")
        self.assertNotIn("secret", str(caught.exception))

    @patch("app.chatgpt.health_mail.smtplib.SMTP")
    def test_plaintext_transport_is_rejected_even_for_invalid_stored_configuration(self, smtp):
        self.config.smtp_security = "none"
        with self.assertRaises(MailDeliveryError):
            send_notification(self.config, "test", "body")
        smtp.assert_not_called()

    @patch("app.chatgpt.health_mail.imaplib.IMAP4_SSL")
    def test_imap_only_authenticates_without_reading_mail(self, imap):
        test_imap(self.config)
        imap.return_value.login.assert_called_once_with("sender@example.com", "secret")
        imap.return_value.select.assert_not_called()
        imap.return_value.logout.assert_called_once()
