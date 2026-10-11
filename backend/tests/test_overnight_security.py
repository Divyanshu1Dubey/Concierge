"""Overnight QA: security boundaries for the growth platform.

Tenant isolation and role matrix over every growth endpoint, SSRF / DNS-rebinding defence of the website
check, output escaping, secret non-disclosure, scheduler secret handling and SMS safety rules.
"""
import base64
import hashlib
import hmac
import json
import socket
from unittest import mock

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.core.security import encrypt_secret
from apps.growth import visibility
from apps.growth.consent import unsubscribe_token
from apps.growth.followups import scan_practice
from apps.growth.models import FollowUpTask, Integration, RecallContact, SmsMessage, VisibilityReport
from apps.practices.models import KnowledgeEntry, Practice, UnansweredQuestion
from apps.users.models import User


def make_user(email, role, practice):
    return User.objects.create_user(username=email, email=email, password='Str0ng-Test-Passphrase-91', role=role, practice=practice)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class TenantFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.a = Practice.objects.create(name='Alpha', slug='alpha', email='a@alpha.test', phone='9195550100', website='https://alpha.test')
        self.b = Practice.objects.create(name='Beta', slug='beta', email='b@beta.test')
        self.admin_a = make_user('admin@alpha.test', 'PRACTICE_ADMIN', self.a)
        self.desk_a = make_user('desk@alpha.test', 'FRONT_DESK', self.a)
        self.admin_b = make_user('admin@beta.test', 'PRACTICE_ADMIN', self.b)
        appt = Appointment.objects.create(practice=self.a, patient_name='Pat A', patient_email='pa@x.test')
        Appointment.objects.filter(id=appt.id).update(created_at=timezone.now() - timezone.timedelta(hours=8))
        scan_practice(self.a)
        self.task = FollowUpTask.objects.get(practice=self.a)
        self.report = VisibilityReport.objects.create(practice=self.a, url='https://alpha.test', score=50)
        self.contact = RecallContact.objects.create(practice=self.a, name='Recall A', email='ra@x.test')
        self.question = UnansweredQuestion.objects.create(practice=self.a, question='Parking?', normalized='parking')
        self.integ = Integration.objects.create(practice=self.a, kind='nexhealth', status='connected',
                                                config={'subdomain': 'alpha', 'location_id': 1},
                                                secret=encrypt_secret(json.dumps({'api_key': 'SUPER-SECRET-KEY-123'})))


# Object-level endpoints owned by practice A: (method, url-builder, body)
OBJECT_ENDPOINTS = [
    ('patch', lambda s: f'/api/v1/growth/follow-ups/{s.task.id}/', {'action': 'dismiss'}),
    ('post', lambda s: f'/api/v1/growth/follow-ups/{s.task.id}/send/', {'subject': 's', 'body': 'b'}),
    ('post', lambda s: f'/api/v1/growth/follow-ups/{s.task.id}/ai-draft/', {}),
    ('get', lambda s: f'/api/v1/growth/visibility/{s.report.id}/', None),
    ('patch', lambda s: f'/api/v1/growth/recall/{s.contact.id}/', {'notes': 'x'}),
    ('delete', lambda s: f'/api/v1/growth/recall/{s.contact.id}/', None),
    ('post', lambda s: f'/api/v1/growth/knowledge-suggest/{s.question.id}/', {}),
]

STAFF_ENDPOINTS = [
    ('get', '/api/v1/growth/follow-ups/'), ('get', '/api/v1/growth/analytics/'), ('get', '/api/v1/growth/briefing/'),
    ('get', '/api/v1/growth/settings/'), ('get', '/api/v1/growth/visibility/'), ('get', '/api/v1/growth/visibility/facts/'),
    ('get', '/api/v1/growth/recall/'), ('get', '/api/v1/growth/contact-preferences/'), ('get', '/api/v1/growth/sms/'),
    ('get', '/api/v1/growth/integrations/'), ('post', '/api/v1/growth/visibility/run/'), ('post', '/api/v1/growth/sms/'),
]

ADMIN_ONLY = [
    ('post', '/api/v1/growth/briefing/send/'), ('post', '/api/v1/growth/recall/import/'),
    ('post', '/api/v1/growth/integrations/google/connect/'), ('get', '/api/v1/growth/integrations/google/locations/'),
    ('post', '/api/v1/growth/integrations/google/posts/'), ('post', '/api/v1/growth/integrations/google/disconnect/'),
    ('post', '/api/v1/growth/integrations/nexhealth/'), ('post', '/api/v1/growth/integrations/nexhealth/test/'),
    ('post', '/api/v1/growth/integrations/nexhealth/disconnect/'), ('post', '/api/v1/growth/integrations/twilio/'),
    ('post', '/api/v1/growth/integrations/twilio/disconnect/'),
]


class IsolationMatrixTests(TenantFixture):
    def test_other_practice_gets_404_on_every_object_endpoint(self):
        other = client_for(self.admin_b)
        for method, url, body in OBJECT_ENDPOINTS:
            r = getattr(other, method)(url(self), body or {}, format='json')
            self.assertEqual(r.status_code, 404, f'{method.upper()} {url(self)} -> {r.status_code}')
        # and nothing changed
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'open')
        self.assertTrue(RecallContact.objects.filter(id=self.contact.id).exists())

    def test_anonymous_rejected_everywhere(self):
        anon = APIClient()
        for method, url in STAFF_ENDPOINTS + ADMIN_ONLY:
            self.assertEqual(getattr(anon, method)(url, {}, format='json').status_code, 401, url)
        for method, url, body in OBJECT_ENDPOINTS:
            self.assertEqual(getattr(anon, method)(url(self), body or {}, format='json').status_code, 401, url(self))

    def test_front_desk_blocked_from_admin_actions(self):
        desk = client_for(self.desk_a)
        for method, url in ADMIN_ONLY:
            self.assertEqual(getattr(desk, method)(url, {}, format='json').status_code, 403, url)
        self.assertEqual(desk.patch('/api/v1/growth/settings/', {'briefing_enabled': False}, format='json').status_code, 403)
        self.assertEqual(desk.delete(f'/api/v1/growth/recall/{self.contact.id}/').status_code, 403)

    def test_list_endpoints_never_show_other_practice_rows(self):
        other = client_for(self.admin_b)
        self.assertEqual(other.get('/api/v1/growth/follow-ups/?status=all').json()['results'], [])
        self.assertEqual(other.get('/api/v1/growth/recall/').json()['results'], [])
        self.assertIsNone(other.get('/api/v1/growth/visibility/').json()['latest'])
        self.assertEqual(other.get(f'/api/v1/growth/follow-ups/?appointment={self.task.appointment_id}').json()['results'], [])
        self.assertEqual(other.get(f'/api/v1/growth/sms/?appointment={self.task.appointment_id}').json()['results'], [])

    def test_cannot_create_follow_up_or_sms_for_other_practice_request(self):
        other = client_for(self.admin_b)
        appt_id = str(self.task.appointment_id)
        self.assertEqual(other.post('/api/v1/growth/follow-ups/', {'appointment_id': appt_id}, format='json').status_code, 404)
        with override_settings(SMS_BACKEND='console'):
            self.assertEqual(other.post('/api/v1/growth/sms/', {'appointment_id': appt_id, 'body': 'hi'}, format='json').status_code, 404)
        self.assertEqual(SmsMessage.objects.count(), 0)

    def test_tenant_staff_cannot_switch_practice_with_header(self):
        r = client_for(self.admin_b).get('/api/v1/growth/recall/', HTTP_X_PRACTICE_ID=str(self.a.id))
        self.assertEqual(r.json()['results'], [])

    def test_agency_admin_can_scope_to_a_practice(self):
        agency = User.objects.create_user(username='ag@x.test', email='ag@x.test', password='Str0ng-Test-Passphrase-91',
                                          role='AGENCY_ADMIN', is_staff=True)
        r = client_for(agency).get('/api/v1/growth/recall/', HTTP_X_PRACTICE_ID=str(self.a.id))
        self.assertEqual([c['name'] for c in r.json()['results']], ['Recall A'])

    def test_integration_secrets_never_returned(self):
        for user in (self.admin_a, self.desk_a):
            body = client_for(user).get('/api/v1/growth/integrations/').content.decode()
            self.assertNotIn('SUPER-SECRET-KEY-123', body)
            self.assertNotIn(self.integ.secret, body)
        self.assertNotIn('SUPER-SECRET-KEY-123', self.integ.secret)

    def test_saving_integration_without_key_keeps_existing_secret(self):
        r = client_for(self.admin_a).post('/api/v1/growth/integrations/nexhealth/', {'subdomain': 'alpha2', 'location_id': '2'}, format='json')
        self.assertEqual(r.status_code, 200)
        from apps.growth.integrations import read_secret
        self.integ.refresh_from_db()
        self.assertEqual(read_secret(self.integ)['api_key'], 'SUPER-SECRET-KEY-123')


# ── SSRF / DNS rebinding ─────────────────────────────────────────────────────────────────────

def _addr(ip):
    fam = socket.AF_INET6 if ':' in ip else socket.AF_INET
    return [(fam, socket.SOCK_STREAM, 6, '', (ip, 0) if fam == socket.AF_INET else (ip, 0, 0, 0))]


BLOCKED_RESOLUTIONS = ['127.0.0.1', '10.1.2.3', '172.16.5.5', '192.168.1.1', '100.64.0.1', '169.254.169.254', '0.0.0.0',
                       '224.0.0.1', '::1', 'fe80::1', 'fc00::1', '::ffff:127.0.0.1', '::ffff:10.0.0.1', '2002:7f00:1::1',
                       '198.18.0.1', '240.0.0.1']


@pytest.mark.parametrize('ip', BLOCKED_RESOLUTIONS)
def test_hostname_resolving_to_non_public_address_is_refused(ip):
    with mock.patch('socket.getaddrinfo', return_value=_addr(ip)):
        with pytest.raises(visibility.CheckError, match='Only public websites'):
            visibility.validate_url('https://innocent-looking.example/')


@pytest.mark.parametrize('url', ['http://127.0.0.1/', 'http://[::1]/', 'http://169.254.169.254/latest/meta-data/',
                                 'http://[fe80::1]/', 'http://10.0.0.1/', 'http://0.0.0.0/'])
def test_ip_literals_refused_without_dns(url):
    with mock.patch('socket.getaddrinfo', side_effect=AssertionError('literal must not be resolved')):
        with pytest.raises(visibility.CheckError):
            visibility.validate_url(url)


@pytest.mark.parametrize('url,msg', [
    ('ftp://alpha.test/', 'http://'), ('javascript:alert(1)', 'not valid|http://'), ('file:///etc/passwd', 'http://'),
    ('http://alpha.test:22/', 'standard web ports'), ('http://user:pw@alpha.test/', 'username or password'),
    ('http://localhost/', 'public'), ('http://intranet/', 'public'), ('http://db.internal/', 'public'),
    ('http://printer.local/', 'public'), ('http://x.localhost/', 'public'), ('https://' + 'a' * 2100 + '.com', 'too long'),
    ('http://[not-an-ip/', 'not valid'),
])
def test_malformed_or_disallowed_urls(url, msg):
    with pytest.raises(visibility.CheckError, match=msg):
        visibility.validate_url(url)


def test_mixed_dns_answer_with_any_private_address_is_refused():
    answer = _addr('93.184.215.14') + _addr('10.0.0.5')
    with mock.patch('socket.getaddrinfo', return_value=answer):
        with pytest.raises(visibility.CheckError):
            visibility.resolve_public('rebind.example')


class _Resp:
    def __init__(self, status=200, headers=None, chunks=(b'<html></html>',), encoding='utf-8'):
        self.status_code, self.headers, self._chunks, self.encoding = status, headers or {}, chunks, encoding

    def iter_content(self, n):
        yield from self._chunks

    def close(self):
        pass


def test_connection_is_pinned_to_the_validated_ip():
    calls = []

    def fake_get(self, url, headers=None, **kw):
        calls.append((url, headers['Host']))
        return _Resp()
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), \
            mock.patch('requests.Session.get', fake_get):
        visibility.safe_get('https://site.example/path?q=1')
    assert calls == [('https://93.184.215.14/path?q=1', 'site.example')]


def test_dns_change_between_check_and_connect_cannot_reach_private_ip():
    """Time-of-check/time-of-use: resolution happens once per hop and the request goes to that address."""
    answers = iter([_addr('93.184.215.14'), _addr('127.0.0.1')])
    calls = []
    with mock.patch('socket.getaddrinfo', side_effect=lambda *a, **k: next(answers)), \
            mock.patch('requests.Session.get', lambda self, url, **kw: calls.append(url) or _Resp()):
        visibility.safe_get('https://flip.example/')
    assert calls == ['https://93.184.215.14/']


def test_redirect_to_private_address_is_blocked_before_connecting():
    calls = []

    def fake_get(self, url, **kw):
        calls.append(url)
        return _Resp(302, {'Location': 'http://169.254.169.254/latest/meta-data/'})
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), mock.patch('requests.Session.get', fake_get):
        with pytest.raises(visibility.CheckError, match='Only public websites'):
            visibility.safe_get('https://site.example/')
    assert len(calls) == 1


def test_redirect_loop_and_oversized_body_are_bounded():
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), \
            mock.patch('requests.Session.get', lambda self, url, **kw: _Resp(302, {'Location': '/again'})):
        with pytest.raises(visibility.CheckError, match='redirects too many times'):
            visibility.safe_get('https://site.example/')
    big = [b'x' * 65536] * 100
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), \
            mock.patch('requests.Session.get', lambda self, url, **kw: _Resp(chunks=big)):
        _, _, _, text, _, size = visibility.safe_get('https://site.example/', max_bytes=200_000)
    assert len(text) <= 200_000 + 65536 and size > 200_000


def test_environment_proxies_are_ignored():
    seen = {}

    def fake_get(self, url, **kw):
        seen['trust_env'] = self.trust_env
        return _Resp()
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), mock.patch('requests.Session.get', fake_get):
        visibility.safe_get('http://site.example/')
    assert seen['trust_env'] is False


def test_bad_encoding_and_invalid_html_do_not_crash():
    with mock.patch('socket.getaddrinfo', return_value=_addr('93.184.215.14')), \
            mock.patch('requests.Session.get', lambda self, url, **kw: _Resp(chunks=(b'\xff\xfe<html><body><<div>', ), encoding='no-such-codec')):
        _, status, _, text, _, _ = visibility.safe_get('https://site.example/')
    assert status == 200 and '<html>' in text


# ── Output escaping ──────────────────────────────────────────────────────────────────────────

class EscapingTests(TenantFixture):
    def test_facts_export_escapes_html_and_script_breakout(self):
        KnowledgeEntry.objects.create(practice=self.a, category='faq', title='<img src=x onerror=alert(1)>',
                                      content='</script><script>alert(2)</script>')
        data = client_for(self.desk_a).get('/api/v1/growth/visibility/facts/').json()
        self.assertNotIn('<img src=x', data['faq_html'])
        self.assertIn('&lt;img', data['faq_html'])
        self.assertEqual(data['faq_structured_data'].count('</script>'), 1)  # only the real closing tag

    def test_unsubscribe_page_escapes_practice_name(self):
        self.a.name = '<script>alert(1)</script>'
        self.a.save()
        body = APIClient().get(f'/api/v1/growth/unsubscribe/{unsubscribe_token(self.a, "x@y.test")}/').content.decode()
        self.assertNotIn('<script>alert(1)</script>', body)
        self.assertIn('&lt;script&gt;', body)

    def test_tampered_unsubscribe_token_rejected(self):
        tok = unsubscribe_token(self.a, 'x@y.test')
        bad = tok[:-2] + ('A' if tok[-2] != 'A' else 'B') + tok[-1]
        r = APIClient().post(f'/api/v1/growth/unsubscribe/{bad}/')
        self.assertIn(b'not valid', r.content)


# ── Scheduler secret ─────────────────────────────────────────────────────────────────────────

class CronSecretTests(TestCase):
    def test_missing_secret_disables_endpoint_entirely(self):
        with override_settings(CRON_SECRET=''):
            self.assertEqual(APIClient().post('/api/v1/growth/cron/run/', {}, format='json', HTTP_X_CRON_SECRET='').status_code, 403)

    def test_rotated_secret_rejects_the_old_one(self):
        with override_settings(CRON_SECRET='old-secret-value'):
            self.assertEqual(APIClient().post('/api/v1/growth/cron/run/', {'jobs': ['cleanup']}, format='json',
                                              HTTP_X_CRON_SECRET='old-secret-value').status_code, 200)
        with override_settings(CRON_SECRET='new-secret-value'):
            self.assertEqual(APIClient().post('/api/v1/growth/cron/run/', {}, format='json',
                                              HTTP_X_CRON_SECRET='old-secret-value').status_code, 403)

    def test_unknown_job_names_ignored(self):
        with override_settings(CRON_SECRET='s'):
            r = APIClient().post('/api/v1/growth/cron/run/', {'jobs': ['__import__', 'cleanup']}, format='json', HTTP_X_CRON_SECRET='s')
        self.assertEqual([x['job'] for x in r.json()['ran']], ['cleanup'])


# ── SMS safety ───────────────────────────────────────────────────────────────────────────────

def _sig(token, url, params):
    payload = url + ''.join(f'{k}{params[k]}' for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()).decode()


@override_settings(SMS_BACKEND='console', TWILIO_ACCOUNT_SID='AC' + 'x' * 32, TWILIO_AUTH_TOKEN='live-token',
                   TWILIO_FROM_NUMBER='+19195550000', APP_PUBLIC_URL='https://app.test')
class SmsSafetyTests(TenantFixture):
    def test_test_mode_wins_over_live_credentials(self):
        from apps.growth.sms import send_sms
        with mock.patch('apps.growth.sms.requests.post', side_effect=AssertionError('must not call Twilio')):
            msg = send_sms(self.a, '9195550123', 'hello')
        self.assertEqual(msg.provider, 'console')

    def test_test_mode_wins_over_practice_credentials(self):
        from apps.growth.sms import send_sms
        Integration.objects.create(practice=self.a, kind='twilio', status='connected', config={'from_number': '+19195550001'},
                                   secret=encrypt_secret(json.dumps({'account_sid': 'AC' + 'y' * 32, 'auth_token': 't'})))
        with mock.patch('apps.growth.sms.requests.post', side_effect=AssertionError('must not call Twilio')):
            self.assertEqual(send_sms(self.a, '9195550123', 'hello').provider, 'console')

    def test_duplicate_or_replayed_webhook_processed_once(self):
        SmsMessage.objects.create(practice=self.a, direction='out', to_number='+19195550199', body='x', provider='twilio')
        params = {'From': '+19195550199', 'To': '+19195550000', 'Body': 'STOP', 'MessageSid': 'SMdup1'}
        url = 'https://app.test/api/v1/growth/sms/inbound/'
        sig = _sig('live-token', url, params)
        for _ in range(3):
            self.assertEqual(APIClient().post('/api/v1/growth/sms/inbound/', params, HTTP_X_TWILIO_SIGNATURE=sig).status_code, 200)
        self.assertEqual(SmsMessage.objects.filter(direction='in').count(), 1)

    def test_status_callback_requires_signature_and_known_message(self):
        m = SmsMessage.objects.create(practice=self.a, direction='out', to_number='+19195550199', body='x', provider='twilio',
                                      provider_id='SMout1', status='sent')
        params = {'MessageSid': 'SMout1', 'MessageStatus': 'delivered'}
        url = 'https://app.test/api/v1/growth/sms/status/'
        self.assertEqual(APIClient().post('/api/v1/growth/sms/status/', params, HTTP_X_TWILIO_SIGNATURE='bad').status_code, 403)
        self.assertEqual(APIClient().post('/api/v1/growth/sms/status/', params, HTTP_X_TWILIO_SIGNATURE=_sig('live-token', url, params)).status_code, 204)
        m.refresh_from_db()
        self.assertEqual(m.status, 'delivered')
        self.assertEqual(APIClient().post('/api/v1/growth/sms/status/', {'MessageSid': ''}).status_code, 204)

    def test_malformed_webhook_payloads(self):
        for params in ({}, {'From': 'not a number', 'To': '', 'Body': ''}, {'Body': 'x' * 5000}):
            r = APIClient().post('/api/v1/growth/sms/inbound/', params, HTTP_X_TWILIO_SIGNATURE='x')
            self.assertEqual(r.status_code, 403)
