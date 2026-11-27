from unittest.mock import patch
from django.test import TestCase
from django.contrib import admin
from django.contrib.auth.models import Permission
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from app.accounts.models import User
from app.accounts.views import UserAccountView, UserSessionRevokeView, BatchUserActionView
from app.accounts.admin import UserAdmin

class AdminTargetSecurityTests(TestCase):
    def setUp(self):
        self.factory=APIRequestFactory()
        self.staff=User.objects.create_user(username='ordinary-staff',password='Test-only-strong-123!',is_staff=True)
        self.root=User.objects.create_superuser(username='extra-superuser',password='Test-only-strong-123!')
        self.user=User.objects.create_user(username='ordinary-user',password='Test-only-strong-123!')
    def request(self,view,method,data,actor=None):
        request=getattr(self.factory,method)('/0x/user/',data,format='json')
        force_authenticate(request,user=actor or self.staff)
        return view.as_view()(request)
    def test_staff_cannot_reset_additional_superuser_password(self):
        response=self.request(UserAccountView,'post',{'username':self.root.username,'password':'Replacement-strong-123!','is_active':True,'isolated_session':True})
        self.assertEqual(response.status_code,403)
        self.root.refresh_from_db();self.assertTrue(self.root.check_password('Test-only-strong-123!'))
    def test_staff_cannot_revoke_additional_superuser_sessions(self):
        token=Token.objects.create(user=self.root)
        response=self.request(UserSessionRevokeView,'post',{'user_id':self.root.pk})
        self.assertEqual(response.status_code,403);self.assertTrue(Token.objects.filter(pk=token.pk).exists())
    def test_bulk_target_checks_are_atomic(self):
        response=self.request(BatchUserActionView,'post',{'user_id_list':[self.user.pk,self.root.pk],'action':'deactivate'})
        self.assertEqual(response.status_code,403)
        self.user.refresh_from_db();self.root.refresh_from_db();self.assertTrue(self.user.is_active and self.root.is_active)
    @patch('app.accounts.views.req_gateway',return_value={})
    def test_staff_can_manage_an_ordinary_user(self,_gateway):
        response=self.request(UserAccountView,'post',{'username':self.user.username,'is_active':True,'isolated_session':True})
        self.assertEqual(response.status_code,200)
    @patch('app.accounts.views.req_gateway',side_effect=ValidationError('simulated gateway failure'))
    def test_password_commit_always_revokes_local_api_tokens(self,_gateway):
        token=Token.objects.create(user=self.user)
        response=self.request(UserAccountView,'post',{'username':self.user.username,'password':'Replacement-strong-123!','is_active':True,'isolated_session':True,'force_chat_mode':False},actor=self.root)
        self.user.refresh_from_db();self.assertTrue(self.user.check_password('Replacement-strong-123!'))
        self.assertFalse(Token.objects.filter(pk=token.pk).exists())
        self.assertEqual(response.status_code,200)
    def test_native_django_admin_denies_target_superuser(self):
        self.staff.user_permissions.add(Permission.objects.get(codename='change_user'))
        request=self.factory.get('/django-admin/accounts/user/');request.user=self.staff
        self.assertFalse(UserAdmin(User,admin.site).has_change_permission(request,self.root))

    def test_staff_cannot_delete_additional_superuser(self):
        response=self.request(UserAccountView,'delete',{'username':self.root.username})
        self.assertEqual(response.status_code,403)
        self.assertTrue(User.objects.filter(pk=self.root.pk).exists())

    def test_staff_cannot_manage_other_staff(self):
        target=User.objects.create_user('second-staff',password='staff-password',is_staff=True)
        response=self.request(UserSessionRevokeView,'post',{'user_id':target.pk})
        self.assertEqual(response.status_code,403)

    def test_batch_cannot_remove_all_superusers(self):
        another=User.objects.create_superuser('another-root',password='root-password')
        response=self.request(BatchUserActionView,'post',{'user_id_list':[self.root.pk,another.pk],'action':'delete'},actor=self.root)
        self.assertEqual(response.status_code,403)
        self.assertEqual(User.objects.filter(is_superuser=True).count(),2)

    @patch('app.accounts.names.req_gateway',return_value={'available':True})
    def test_deleted_name_is_reserved_and_old_backup_without_tombstones_still_restores(self,gateway):
        from app.accounts.names import ensure_username_available
        from app.accounts.models import RetiredUsername
        from app.accounts.views.backup import _export_django_data,_restore_complete_django
        self.user.delete()
        self.assertTrue(RetiredUsername.objects.filter(name='ordinary-user').exists())
        with self.assertRaises(ValidationError):ensure_username_available('ordinary-user')
        payload=_export_django_data()
        payload.pop('retired_usernames')
        _restore_complete_django(payload)
        self.assertTrue(User.objects.filter(username='extra-superuser').exists())
        self.assertTrue(RetiredUsername.objects.filter(name='ordinary-user').exists())

    @patch('app.accounts.names.req_gateway',return_value={'available':False})
    def test_legacy_gateway_resources_prevent_name_reuse(self,gateway):
        from app.accounts.names import ensure_username_available
        with self.assertRaises(ValidationError):ensure_username_available('historic-deleted-user')
        gateway.assert_called_once()

    @patch('app.accounts.work_mode_sync.req_gateway',return_value={})
    def test_mode_sync_retry_uses_current_value_and_is_idempotent(self,gateway):
        from app.accounts.models import UserWorkModeSync
        from app.accounts.work_mode_sync import enqueue,deliver
        enqueue(self.user)
        job=UserWorkModeSync.objects.get(user=self.user)
        self.user.force_chat_mode=True
        self.user.save(update_fields=['force_chat_mode'])
        deliver(job.pk)
        deliver(job.pk)
        gateway.assert_called_once()
        self.assertTrue(gateway.call_args.kwargs['json']['force_chat_mode'])
        self.assertFalse(UserWorkModeSync.objects.exists())

    def test_superuser_revocation_also_clears_its_native_admin_session_only(self):
        from django.test import Client
        from django.contrib.sessions.models import Session
        target=Client();target.force_login(self.root)
        other=Client();other.force_login(self.staff)
        root_key=target.session.session_key
        staff_key=other.session.session_key
        response=self.request(UserSessionRevokeView,'post',{'user_id':self.root.pk},actor=self.root)
        self.assertEqual(response.status_code,200)
        self.assertFalse(Session.objects.filter(session_key=root_key).exists())
        self.assertTrue(Session.objects.filter(session_key=staff_key).exists())

    @patch('app.accounts.views.revoke_user_sessions',side_effect=RuntimeError('synthetic local storage failure'))
    def test_failed_local_revocation_rolls_back_the_password_change(self,revoke):
        token=Token.objects.create(user=self.user)
        with self.assertRaises(RuntimeError):
            self.request(UserAccountView,'post',{'username':self.user.username,'password':'Replacement-strong-123!','is_active':True,'isolated_session':True},actor=self.root)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Test-only-strong-123!'))
        self.assertTrue(Token.objects.filter(pk=token.pk).exists())

    def test_stale_superuser_flag_cannot_authorize_a_pool_write_after_demotion(self):
        from app.chatgpt.models import ChatgptCar
        from app.chatgpt.views.gptcar import GptCarUserAssignmentView
        pool=ChatgptCar.objects.create(car_name='security-test-pool',created_time=1,updated_time=1)
        User.objects.filter(pk=self.root.pk).update(is_superuser=False)
        req=self.factory.post('/0x/chatgpt/car/',{'user_ids':[self.staff.pk]},format='json')
        force_authenticate(req,user=self.root)
        response=GptCarUserAssignmentView.as_view()(req,car_id=pool.pk)
        self.assertEqual(response.status_code,403)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.gptcar_list,[])

    @patch('app.accounts.views.req_gateway')
    def test_staff_cannot_reset_superuser_conversation_statistics(self,gateway):
        from app.accounts.views import UserConversationStatisticsView
        req=self.factory.delete('/0x/user/conversation-statistics/'+str(self.root.pk),format='json')
        force_authenticate(req,user=self.staff)
        response=UserConversationStatisticsView.as_view()(req,user_id=self.root.pk)
        self.assertEqual(response.status_code,403)
        gateway.assert_not_called()
