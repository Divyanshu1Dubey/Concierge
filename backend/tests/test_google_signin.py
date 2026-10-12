"""Sign in with Google: staff-only adapter, one-time code hand-off, configuration flag, https callback."""
from datetime import timedelta
from unittest import mock

from allauth.core.exceptions import ImmediateHttpResponse
from django.core import signing
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.practices.models import Practice
from apps.users import google_auth
from apps.users.models import User


def fake_login(email, verified=True, existing=False, linked_user=None, sub='g-123'):
    sl = mock.Mock()
    sl.account.extra_data = {'email': email, 'email_verified': verified, 'sub': sub}
    sl.account.uid = sub
    sl.is_existing = existing
    sl.user = linked_user or mock.Mock(email=email, pk=None)
    return sl


class AdapterTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        self.user = User.objects.create_user(username='doc@x.test', email='doc@x.test', password='Str0ng-Test-Passphrase-91',
                                             role='PRACTICE_ADMIN', practice=self.p)
        self.adapter = google_auth.StaffOnlyGoogleAdapter()
        self.req = RequestFactory().get('/')

    def refused(self, sl):
        with self.assertRaises(ImmediateHttpResponse) as ctx:
            self.adapter.pre_social_login(self.req, sl)
        return ctx.exception.response['Location']

    def test_never_open_for_signup(self):
        self.assertFalse(self.adapter.is_open_for_signup(self.req, mock.Mock()))

    def test_unknown_email_refused(self):
        self.assertIn('google=no_account', self.refused(fake_login('stranger@gmail.com')))

    def test_unverified_email_refused(self):
        self.assertIn('google=unverified', self.refused(fake_login('doc@x.test', verified=False)))

    def test_disabled_and_suspended_refused(self):
        self.user.is_active = False
        self.user.save()
        self.assertIn('google=disabled', self.refused(fake_login('doc@x.test')))
        self.user.is_active = True
        self.user.save()
        self.p.active = False
        self.p.save()
        self.assertIn('google=suspended', self.refused(fake_login('DOC@x.test')))

    def test_existing_staff_is_linked_case_insensitively(self):
        sl = fake_login('Doc@X.test')
        self.adapter.pre_social_login(self.req, sl)
        sl.connect.assert_called_once_with(self.req, self.user)
        self.user.refresh_from_db()
        self.assertEqual(self.user.google_id, 'g-123')

    def test_google_identity_linked_to_another_user_is_refused(self):
        other = User.objects.create_user(username='o@x.test', email='o@x.test', password='Str0ng-Test-Passphrase-91',
                                         role='FRONT_DESK', practice=self.p)
        sl = fake_login('doc@x.test', existing=True, linked_user=other)
        self.assertIn('google=no_account', self.refused(sl))


class HandOffTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        self.user = User.objects.create_user(username='doc@x.test', email='doc@x.test', password='Str0ng-Test-Passphrase-91',
                                             role='PRACTICE_ADMIN', practice=self.p)
        self.user.last_login = timezone.now() - timedelta(seconds=5)
        self.user.save()

    def test_complete_without_session_goes_back_to_login(self):
        r = self.client.get('/api/auth/google/complete/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login?google=failed', r['Location'])

    def test_complete_hands_code_in_fragment_and_drops_session(self):
        self.client.force_login(self.user)
        r = self.client.get('/api/auth/google/complete/')
        self.assertIn('/login#google_code=', r['Location'])
        self.assertNotIn('_auth_user_id', self.client.session)  # cookie session dropped
        code = r['Location'].split('google_code=')[1]
        ok = APIClient().post('/api/auth/google/exchange/', {'code': code}, format='json')
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()['user']['email'], 'doc@x.test')
        self.assertIn('access', ok.json())
        again = APIClient().post('/api/auth/google/exchange/', {'code': code}, format='json')
        self.assertEqual(again.status_code, 400)  # single use

    def test_expired_forged_and_suspended_codes(self):
        code = google_auth._code_for(self.user)
        with mock.patch('time.time', return_value=__import__('time').time() + 600):
            self.assertEqual(APIClient().post('/api/auth/google/exchange/', {'code': code}, format='json').status_code, 400)
        self.assertEqual(APIClient().post('/api/auth/google/exchange/', {'code': 'forged'}, format='json').status_code, 400)
        forged = signing.dumps({'u': str(self.user.pk), 'l': 'x'}, salt='other-salt')
        self.assertEqual(APIClient().post('/api/auth/google/exchange/', {'code': forged}, format='json').status_code, 400)
        self.p.active = False
        self.p.save()
        self.assertEqual(APIClient().post('/api/auth/google/exchange/', {'code': google_auth._code_for(self.user)}, format='json').status_code, 403)


class ConfigTests(TestCase):
    def test_flag_follows_configuration(self):
        self.assertFalse(APIClient().get('/api/auth/config/').json()['google_enabled'])
        with override_settings(GOOGLE_OAUTH_CLIENT_ID='cid.apps.googleusercontent.com', GOOGLE_OAUTH_CLIENT_SECRET='s'):
            self.assertTrue(APIClient().get('/api/auth/config/').json()['google_enabled'])

    @override_settings(ACCOUNT_DEFAULT_HTTP_PROTOCOL='https',
                       SOCIALACCOUNT_PROVIDERS={'google': {'SCOPE': ['profile', 'email'], 'AUTH_PARAMS': {'access_type': 'online'},
                                                           'APPS': [{'client_id': 'cid.apps.googleusercontent.com', 'secret': 's', 'key': ''}]}})
    def test_login_redirects_to_google_with_https_callback(self):
        r = self.client.get('/api/auth/google/login/', HTTP_HOST='localhost')
        self.assertEqual(r.status_code, 302)
        loc = r['Location']
        self.assertTrue(loc.startswith('https://accounts.google.com/'))
        self.assertIn('redirect_uri=https%3A%2F%2Flocalhost%2Fapi%2Fauth%2Fgoogle%2Flogin%2Fcallback%2F', loc)
        self.assertIn('client_id=cid.apps.googleusercontent.com', loc)
