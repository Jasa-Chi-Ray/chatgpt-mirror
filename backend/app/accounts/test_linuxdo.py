import os
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from app.accounts.models import User, OAuthFlow, OAuthIdentity, LoginGuardMutex, LoginFailureState, PendingLogin
from app.accounts.session_authority import digest
from app.accounts.login_guard import anchor, COOKIE
from app.accounts.linuxdo_config import load_linuxdo
from app.accounts.views.linuxdo import eligible, provider_profile
from app.accounts.views.backup import _export_django_data, _restore_complete_django

FP = {key: char * 64 for key,char in zip(('canvas','webgl','fonts','layout'), 'abcd')}
FP['shape'] = '0123456789abcdef'
PROFILE = {'id':'12345', 'username':'forum-user'}
BASE = '/0x/user/oauth/linuxdo/'

@override_settings(LINUXDO_OAUTH_ENABLED=True, LINUXDO_CLIENT_ID='test-client', LINUXDO_CLIENT_SECRET='test-private',
    LINUXDO_REDIRECT_URI='http://testserver/0x/user/oauth/linuxdo/callback', LINUXDO_MIN_TRUST_LEVEL=0,
    ALLOW_REGISTER=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class LinuxDOTests(TestCase):
    def setUp(self):
        cache.clear()
        self.gateway=patch('app.accounts.revocations.req_gateway', return_value={}).start()
        self.addCleanup(patch.stopall)
        self.user=User.objects.create_user('member', password='test-password')
        LoginGuardMutex.objects.get_or_create(pk=1)
        self.client=self.browser()

    def browser(self):
        client=APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.post('/0x/user/login-status', {'fingerprint':FP}, format='json').status_code,200)
        self.assertEqual(client.get('/0x/user/version-cfg').status_code,200)
        return client

    def post(self, action, data=None, client=None):
        client=client or self.client
        return client.post(BASE+action,data or {},format='json',HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
                           HTTP_USER_AGENT='local-test')

    def start(self, intent='login'):
        r=self.post('start',{'intent':intent})
        self.assertEqual(r.status_code,200,r.data)
        query=parse_qs(urlsplit(r.data['authorize_url']).query)
        self.assertEqual(query['client_id'],['test-client'])
        self.assertNotIn('test-private',r.content.decode())
        return query['state'][0]

    def callback(self,state,profile=None,**params):
        with patch('app.accounts.views.linuxdo.provider_profile', return_value=profile or PROFILE) as provider:
            r=self.client.get(BASE+'callback',{'state':state,'code':'one-time-code',**params})
        self.assertEqual(r.status_code,302)
        self.assertEqual(r['Referrer-Policy'],'no-referrer')
        return r,parse_qs(urlsplit(r['Location']).fragment.split('?',1)[1]),provider

    def ready(self,profile=None,intent='login'):
        state=self.start(intent)
        r,query,provider=self.callback(state,profile)
        self.assertTrue(provider.called)
        return query['linuxdo_result'][0],state

    def auth(self,user=None):
        token=Token.objects.create(user=user or self.user)
        self.client.cookies['mirror_api_session']=token.key
        return token

    def block(self):
        return LoginFailureState.objects.create(key='blocked',account_digest='x',ip='127.0.0.1',fingerprint=FP,
            fingerprint_anchor=anchor(FP),failures=5,blocked_until=timezone.now()+timedelta(seconds=120))

    def test_closed_registration_requires_password_and_confirms_once(self):
        ticket,state=self.ready()
        self.assertEqual(self.post('complete',{'result':ticket}).data['requires_binding'],True)
        self.assertEqual(User.objects.count(),1)
        self.assertFalse(OAuthIdentity.objects.exists())
        r=self.post('bind-login',{'result':ticket,'username':'member','password':'test-password'})
        self.assertEqual(r.status_code,200,r.data)
        self.assertIn('login_ticket',r.data)
        self.assertNotIn('mirror_api_session',r.cookies)
        self.assertEqual(OAuthIdentity.objects.get().user,self.user)
        login_ticket=r.data['login_ticket']
        r=self.client.post('/0x/user/login-confirm',{'login_ticket':login_ticket},format='json',HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value, HTTP_USER_AGENT='local-test')
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data['username'],'member')
        self.assertTrue(r.data['authenticated'])
        self.assertTrue(r.cookies['mirror_api_session']['httponly'])
        self.assertFalse(OAuthFlow.objects.exists())
        self.assertEqual(self.post('complete',{'result':ticket}).status_code,400)

    @override_settings(ALLOW_REGISTER=True)
    def test_auto_registration_creates_ordinary_isolated_account(self):
        collision=User.objects.create_superuser('linuxdo_12345',password='admin-password')
        ticket,_=self.ready()
        r=self.post('complete',{'result':ticket})
        self.assertEqual(r.status_code,200,r.data)
        account=OAuthIdentity.objects.get().user
        self.assertNotEqual(account,collision)
        self.assertFalse(account.is_staff or account.is_superuser or account.has_usable_password())
        self.assertTrue(account.isolated_session and account.mcp_isolation and account.skills_isolation)
        self.assertEqual(account.gptcar_list,[])
        self.assertEqual(PendingLogin.objects.get().user,account)
        self.assertEqual(User.objects.count(),3)

    def test_existing_link_works_without_registration_and_updates_rename(self):
        OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='12345',username='old')
        ticket,_=self.ready()
        r=self.post('complete',{'result':ticket})
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(PendingLogin.objects.get().user,self.user)
        self.assertEqual(OAuthIdentity.objects.get().username,'forum-user')
        self.assertEqual(User.objects.count(),1)

    def test_state_browser_binding_and_callback_one_use(self):
        state=self.start()
        stranger=self.browser()
        with patch('app.accounts.views.linuxdo.provider_profile') as provider:
            r=stranger.get(BASE+'callback',{'state':state,'code':'x'})
            self.assertIn('linuxdo_error=expired',r['Location'])
            provider.assert_not_called()
        r,q,p=self.callback(state)
        self.assertIn('linuxdo_result',q)
        r,q,p=self.callback(state)
        self.assertEqual(q['linuxdo_error'],['expired'])
        p.assert_not_called()

    def test_result_is_browser_bound_not_raw_state_or_provider_token(self):
        ticket,state=self.ready()
        flow=OAuthFlow.objects.get()
        self.assertEqual(flow.state_digest,digest(state))
        self.assertEqual(flow.result_digest,digest(ticket))
        self.assertEqual(flow.profile,PROFILE)
        stranger=self.browser()
        self.assertEqual(self.post('complete',{'result':ticket},stranger).status_code,400)
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_parameter_pollution_and_expiry(self):
        state=self.start()
        with patch('app.accounts.views.linuxdo.provider_profile') as provider:
            for query in ({'state':[state,state],'code':'a'}, {'state':state,'code':['a','b']}):
                r=self.client.get(BASE+'callback',query)
                self.assertIn('linuxdo_error=',r['Location'])
            provider.assert_not_called()
        state=self.start()
        OAuthFlow.objects.filter(state_digest=digest(state)).update(expires_at=timezone.now()-timedelta(seconds=1))
        _,q,p=self.callback(state)
        self.assertEqual(q['linuxdo_error'],['expired'])
        p.assert_not_called()

    def test_cancel_and_provider_exception_are_sanitized(self):
        state=self.start()
        r,q,p=self.callback(state,error='access_denied',error_description='<script>private</script>')
        self.assertEqual(q['linuxdo_error'],['cancelled'])
        p.assert_not_called()
        state=self.start()
        with patch('app.accounts.views.linuxdo.provider_profile',side_effect=ValueError('token-secret')):
            r=self.client.get(BASE+'callback',{'state':state,'code':'x'})
        self.assertIn('linuxdo_error=failed',r['Location'])
        self.assertNotIn('token-secret',r['Location'])
        self.assertFalse(OAuthFlow.objects.exists())

    def test_disabled_expired_and_shared_accounts_rejected(self):
        for change in ({'is_active':False},{'expired_date':timezone.localdate()},{'username':'free_account'}):
            with self.subTest(change=change):
                for key,value in change.items(): setattr(self.user,key,value)
                self.user.save()
                OAuthIdentity.objects.all().delete()
                OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='12345')
                ticket,_=self.ready()
                self.assertEqual(self.post('complete',{'result':ticket}).status_code,400)
                self.assertFalse(PendingLogin.objects.exists())
                self.user.is_active=True; self.user.expired_date=None; self.user.username='member'; self.user.save()

    def test_admin_can_bind_through_password_login(self):
        self.user.is_staff=True; self.user.is_superuser=True; self.user.save()
        ticket,_=self.ready()
        r=self.post('bind-login',{'result':ticket,'username':'member','password':'test-password'})
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(OAuthIdentity.objects.get().user,self.user)

    def test_link_from_user_or_admin_profile(self):
        for admin in (False,True):
            with self.subTest(admin=admin):
                Token.objects.all().delete(); OAuthIdentity.objects.all().delete()
                self.user.is_staff=admin; self.user.is_superuser=admin; self.user.save()
                self.auth()
                ticket,_=self.ready(intent='link')
                r=self.post('complete',{'result':ticket})
                self.assertEqual(r.data,{'linked':True})
                data=self.client.get(BASE+'connection').data
                self.assertTrue(data['linked'] and data['can_unlink'])
                self.assertEqual(data['username'],'forum-user')
                r=self.client.delete(BASE+'connection',HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,HTTP_USER_AGENT='local-test')
                self.assertEqual(r.status_code,200,r.data)
                self.assertFalse(OAuthIdentity.objects.exists())

    def test_link_requires_same_session_and_unbound_identity(self):
        token=self.auth()
        ticket,_=self.ready(intent='link')
        token.delete(); self.auth()
        self.assertEqual(self.post('complete',{'result':ticket}).status_code,403)
        self.assertFalse(OAuthIdentity.objects.exists())
        self.assertEqual(self.post('start',{'intent':'bad'}).status_code,400)
        self.client.cookies.pop('mirror_api_session')
        self.assertEqual(self.post('start',{'intent':'link'}).status_code,403)

    def test_provider_identity_cannot_move_between_local_accounts(self):
        other=User.objects.create_user('other',password='other-password')
        OAuthIdentity.objects.create(user=other,provider='linuxdo',subject='12345')
        self.auth()
        ticket,_=self.ready(intent='link')
        self.assertEqual(self.post('complete',{'result':ticket}).status_code,400)
        self.assertEqual(OAuthIdentity.objects.get().user,other)

    def test_local_account_cannot_bind_second_identity(self):
        OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='999')
        ticket,_=self.ready()
        r=self.post('bind-login',{'result':ticket,'username':'member','password':'test-password'})
        self.assertEqual(r.status_code,400)
        self.assertEqual(OAuthIdentity.objects.get().subject,'999')

    def test_missing_fingerprint_and_csrf_are_rejected(self):
        r=self.client.post(BASE+'start',{'intent':'login'},format='json')
        self.assertEqual(r.status_code,403)
        self.client.cookies.pop(COOKIE)
        self.assertEqual(self.post('start',{'intent':'login'}).status_code,401)

    def test_cooldown_survives_cross_site_callback_without_strict_cookie(self):
        state=self.start()
        self.block()
        self.client.cookies.pop(COOKIE)
        r,q,p=self.callback(state)
        self.assertEqual(q['linuxdo_error'],['unavailable'])
        p.assert_not_called()
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_cooldown_blocks_completion_but_not_authenticated_link(self):
        ticket,_=self.ready()
        self.block()
        self.assertEqual(self.post('complete',{'result':ticket}).status_code,401)
        self.auth()
        ticket,_=self.ready(intent='link')
        self.assertEqual(self.post('complete',{'result':ticket}).data,{'linked':True})
        self.assertEqual(self.client.get('/0x/user/me').status_code,200)

    def test_bad_binding_password_counts_towards_cooldown(self):
        ticket,_=self.ready()
        for i in range(5):
            r=self.post('bind-login',{'result':ticket,'username':'member','password':'incorrect'})
            self.assertEqual(r.status_code,401 if i==4 else 400,r.data)
        self.assertEqual(LoginFailureState.objects.get().failures,5)
        self.assertEqual(self.post('bind-login',{'result':ticket,'username':'member','password':'test-password'}).status_code,401)
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_unusable_password_cannot_unlink_last_login(self):
        self.user.set_unusable_password(); self.user.save()
        OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='12345')
        self.auth()
        self.assertFalse(self.client.get(BASE+'connection').data['can_unlink'])
        self.assertEqual(self.client.delete(BASE+'connection',HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value).status_code,400)
        self.assertTrue(OAuthIdentity.objects.exists())

    def test_connection_is_private_and_bootstrap_has_no_credentials(self):
        OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='12345',username='private-name')
        self.assertEqual(self.client.get(BASE+'connection').status_code,401)
        other=User.objects.create_user('other',password='other-password')
        self.auth(other)
        self.assertEqual(self.client.get(BASE+'connection').data['username'],'')
        r=self.client.get('/0x/user/version-cfg')
        self.assertTrue(r.data['linuxdo_enabled'])
        self.assertNotIn('test-private',r.content.decode())
        self.assertNotIn('test-client',r.content.decode())

    def test_backup_preserves_identity_but_not_authorization_flows(self):
        OAuthIdentity.objects.create(user=self.user,provider='linuxdo',subject='12345',username='forum-user')
        self.start()
        payload=_export_django_data()
        self.assertEqual(payload['oauth_identities'][0]['subject'],'12345')
        self.assertNotIn('oauth_flows',payload)
        _restore_complete_django(payload)
        self.assertEqual(OAuthIdentity.objects.get().user.username,'member')
        self.assertFalse(OAuthFlow.objects.exists())
        payload.pop('oauth_identities')
        _restore_complete_django(payload) # v2 backup made before OAuth remains valid
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_bad_backup_binding_rolls_back(self):
        payload=_export_django_data()
        payload['oauth_identities']=[{'provider':'linuxdo','subject':'1','local_username':'missing'}]
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError): _restore_complete_django(payload)
        self.assertEqual(User.objects.get().username,'member')

    @override_settings(LINUXDO_OAUTH_ENABLED=False)
    def test_disabled_start_does_not_create_flow(self):
        self.assertEqual(self.post('start').status_code,400)
        self.assertFalse(OAuthFlow.objects.exists())

    def test_unlink_revokes_oauth_pending_but_keeps_password_pending_and_session(self):
        OAuthIdentity.objects.create(user=self.user, provider='linuxdo', subject='12345')
        result, _ = self.ready()
        prepared = self.post('complete', {'result': result})
        oauth_ticket = prepared.data['login_ticket']
        password_ticket = PendingLogin.objects.create(digest='f' * 64, user=self.user,
            password_digest=digest(self.user.password), csrf_digest='c' * 64,
            expires_at=timezone.now() + timedelta(seconds=60))
        defender = self.browser()
        defender.cookies['mirror_api_session'] = Token.objects.create(user=self.user).key
        response = defender.delete(BASE + 'connection',
            HTTP_X_CSRFTOKEN=defender.cookies['csrftoken'].value, HTTP_USER_AGENT='local-test')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(PendingLogin.objects.filter(pk=password_ticket.pk).exists())
        response = self.client.post('/0x/user/login-confirm', {'login_ticket': oauth_ticket},
            format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
            HTTP_USER_AGENT='local-test')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(defender.get('/0x/user/me').status_code, 200)

    def test_invalid_result_does_not_check_another_accounts_password(self):
        from rest_framework.authtoken.serializers import AuthTokenSerializer
        self.auth()
        with patch('app.accounts.views.linuxdo.AuthTokenSerializer', wraps=AuthTokenSerializer) as serializer:
            response = self.post('bind-login', {'result': '0' * 64,
                'username': 'member', 'password': 'test-password'})
        self.assertEqual(response.status_code, 400, response.data)
        serializer.assert_not_called()

    def test_authenticated_password_attempts_cool_down_without_revoking_session(self):
        result, _ = self.ready()
        self.auth()
        for attempt in range(5):
            response = self.post('bind-login', {'result': result,
                'username': 'member', 'password': 'incorrect'})
            self.assertEqual(response.status_code, 401 if attempt == 4 else 400, response.data)
        self.assertEqual(self.client.get('/0x/user/me').status_code, 200)
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_authenticated_login_callback_survives_cross_site_cookie_rules_and_cooldown(self):
        OAuthIdentity.objects.create(user=self.user, provider='linuxdo', subject='12345')
        self.auth()
        state = self.start()
        self.block()
        receipt = self.client.cookies.pop(COOKIE)
        session = self.client.cookies.pop('mirror_api_session')
        _, query, _ = self.callback(state)
        self.assertIn('linuxdo_result', query)
        self.client.cookies[COOKIE] = receipt.value
        self.client.cookies['mirror_api_session'] = session.value
        response = self.post('complete', {'result': query['linuxdo_result'][0]})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('login_ticket', response.data)

    def test_callback_admission_does_not_bypass_completion_after_session_revocation(self):
        token = self.auth()
        state = self.start()
        self.block()
        receipt = self.client.cookies.pop(COOKIE)
        self.client.cookies.pop('mirror_api_session')
        _, query, _ = self.callback(state)
        self.assertIn('linuxdo_result', query)
        self.client.cookies[COOKIE] = receipt.value
        self.client.cookies['mirror_api_session'] = token.key
        token.delete()
        response = self.post('complete', {'result': query['linuxdo_result'][0]})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(PendingLogin.objects.exists())

    def test_authenticated_password_binding_still_requires_a_rendering_receipt(self):
        result, _ = self.ready()
        self.auth()
        self.client.cookies.pop(COOKIE)
        response = self.post('bind-login', {'result': result,
            'username': 'member', 'password': 'test-password'})
        self.assertEqual(response.status_code, 401)
        self.assertFalse(OAuthIdentity.objects.exists())

    def test_existing_session_can_renew_receipt_without_being_blocked(self):
        self.auth()
        self.client.cookies.pop(COOKIE)
        response = self.client.post('/0x/user/login-status', {'fingerprint': FP}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['remaining_seconds'], 0)
        self.assertIn(COOKIE, response.cookies)
        result, _ = self.ready()
        response = self.post('bind-login', {'result': result,
            'username': 'member', 'password': 'test-password'})
        self.assertEqual(response.status_code, 200, response.data)

    def test_authenticated_password_guesses_are_limited_across_login_endpoints(self):
        from app.accounts.views.login import PasswordAttemptRateThrottle
        self.auth()
        for _ in range(10):
            response = self.client.post('/0x/user/login', {'username': 'member', 'password': 'incorrect'},
                format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value,
                HTTP_USER_AGENT='local-test')
            self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post('/0x/user/login', {'username': 'member', 'password': 'incorrect'},
            format='json', HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(self.post('bind-login', {'result': '0' * 64}).status_code, 429)
        self.assertEqual(self.client.get('/0x/user/me').status_code, 200)

    def test_existing_session_status_does_not_require_rendering_or_apply_cooldown(self):
        self.auth()
        self.block()
        self.client.cookies.pop(COOKIE)
        response = self.client.post('/0x/user/login-status', {'fingerprint': {}}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['remaining_seconds'], 0)
        self.assertEqual(self.client.get('/0x/user/me').status_code, 200)

    @override_settings(ALLOW_REGISTER=True, ADMIN_USERNAME='linuxdo_12345')
    def test_auto_registration_does_not_claim_reserved_admin_username(self):
        result, _ = self.ready()
        response = self.post('complete', {'result': result})
        self.assertEqual(response.status_code, 200, response.data)
        account = OAuthIdentity.objects.get().user
        self.assertNotEqual(account.username, 'linuxdo_12345')
        self.assertFalse(account.is_staff or account.is_superuser)

    @override_settings(ALLOW_REGISTER=True)
    def test_forged_owner_roles_and_pools_do_not_grant_admin_access(self):
        result, _ = self.ready(profile={'id': '23456', 'username': 'admin'})
        response = self.post('complete', {'result': result, 'user_id': self.user.pk,
            'username': 'admin', 'is_staff': True, 'is_superuser': True,
            'is_admin': True, 'gptcar_list': [1], 'isolated_session': False})
        self.assertEqual(response.status_code, 200, response.data)
        account = OAuthIdentity.objects.get().user
        self.assertNotEqual(account, self.user)
        self.assertTrue(account.isolated_session)
        self.assertEqual(account.gptcar_list, [])
        response = self.client.post('/0x/user/login-confirm',
            {'login_ticket': response.data['login_ticket']}, format='json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value, HTTP_USER_AGENT='local-test')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['is_admin'])
        for endpoint in ('/0x/user/', '/0x/user/backup'):
            self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.assertEqual(self.client.post('/0x/user/backup', {}, format='json',
            HTTP_X_CSRFTOKEN=self.client.cookies['csrftoken'].value).status_code, 403)

class ConfigTests(SimpleTestCase):
    def test_requires_explicit_enable_even_with_client_credentials(self):
        with patch.dict(os.environ, {'LINUXDO_CLIENT_ID':'id','LINUXDO_CLIENT_SECRET':'secret',
                'LINUXDO_REDIRECT_URI':'http://127.0.0.1:40002/0x/user/oauth/linuxdo/callback'}):
            os.environ.pop('LINUXDO_OAUTH_ENABLED',None)
            self.assertFalse(load_linuxdo(True)[0])
            with patch.dict(os.environ, {'LINUXDO_OAUTH_ENABLED':'disable'}):
                self.assertFalse(load_linuxdo(True)[0])

    def test_config_validation(self):
        base={'LINUXDO_OAUTH_ENABLED':'enable','LINUXDO_CLIENT_ID':'id','LINUXDO_CLIENT_SECRET':'secret',
              'LINUXDO_REDIRECT_URI':'http://127.0.0.1:40002/0x/user/oauth/linuxdo/callback'}
        with patch.dict(os.environ,base):
            self.assertTrue(load_linuxdo(True)[0])
            with self.assertRaises(ImproperlyConfigured): load_linuxdo(False)
            for bad in ('http://[bad','https://host:bad/0x/user/oauth/linuxdo/callback','https://host/wrong','https://host/0x/user/oauth/linuxdo/callback?x=y'):
                with patch.dict(os.environ,{'LINUXDO_REDIRECT_URI':bad}):
                    with self.assertRaises(ImproperlyConfigured): load_linuxdo(True)
            with patch.dict(os.environ,{'LINUXDO_MIN_TRUST_LEVEL':'5'}):
                with self.assertRaises(ImproperlyConfigured): load_linuxdo(True)
            with patch.dict(os.environ,{'LINUXDO_CLIENT_SECRET':''}):
                with self.assertRaises(ImproperlyConfigured): load_linuxdo(True)

    @override_settings(LINUXDO_MIN_TRUST_LEVEL=2)
    def test_profile_eligibility_and_data_minimization(self):
        profile={'id':12345,'username':'new-name','active':True,'silenced':False,'trust_level':2,'api_key':'private','external_ids':['private']}
        self.assertEqual(eligible(profile),{'id':'12345','username':'new-name'})
        for key,bad in (('active',False),('silenced',True),('trust_level',1),('trust_level',True),('id',True),('username','line\nbreak')):
            with self.subTest(key=key,bad=bad):
                with self.assertRaises(ValueError): eligible({**profile,key:bad})

    @override_settings(LINUXDO_CLIENT_ID='client',LINUXDO_CLIENT_SECRET='secret',LINUXDO_REDIRECT_URI='https://mirror/0x/user/oauth/linuxdo/callback',LINUXDO_MIN_TRUST_LEVEL=0)
    def test_provider_exchange_uses_fixed_endpoints_and_never_retains_token(self):
        token=MagicMock(status_code=200,content=b'{}'); token.json.return_value={'access_token':'provider-token'}; token.__enter__.return_value=token
        user=MagicMock(status_code=200,content=b'{}'); user.json.return_value={'id':12345,'username':'forum-user','active':True,'silenced':False,'trust_level':0,'api_key':'private'}; user.__enter__.return_value=user
        with patch('app.accounts.views.linuxdo.requests.post',return_value=token) as post,patch('app.accounts.views.linuxdo.requests.get',return_value=user) as get:
            self.assertEqual(provider_profile('one-time-code'),PROFILE)
            self.assertEqual(post.call_args.args[0],'https://connect.linux.do/oauth2/token')
            self.assertEqual(post.call_args.kwargs['data']['client_secret'],'secret')
            self.assertFalse(post.call_args.kwargs['allow_redirects'])
            self.assertEqual(get.call_args.kwargs['headers']['Authorization'],'Bearer provider-token')
            token.json.return_value={'access_token':'bad\r\nheader'}
            with self.assertRaises(ValueError): provider_profile('code')
