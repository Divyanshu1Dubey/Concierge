"""Overnight QA: integration adapters with mocked HTTP (Google Business Profile, NexHealth, Twilio live path).

These prove request shapes, error handling and credential handling. They are NOT evidence that the live
services accept these calls; see docs/GROWTH.md for each integration's real verification status.
"""
import json
from datetime import timedelta
from unittest import mock

import requests
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.core.security import encrypt_secret
from apps.growth import integrations as I
from apps.growth.models import Integration, SmsMessage
from apps.practices.models import Practice


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data if data is not None else {}
        self.content = json.dumps(self._data).encode() if data is not None else b''

    def json(self):
        return self._data


@override_settings(GOOGLE_BUSINESS_CLIENT_ID='cid', GOOGLE_BUSINESS_CLIENT_SECRET='csec', APP_PUBLIC_URL='https://app.test')
class GoogleBusinessTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test', phone='9195550100')
        self.integ = Integration.objects.create(practice=self.p, kind='google_business', status='connected',
                                                config={'account': 'accounts/1', 'location': 'locations/2', 'title': 'Alpha'})
        self._tokens(expires=timezone.now() + timedelta(hours=1))

    def _tokens(self, expires, refresh='rt'):
        I.write_secret(self.integ, {'access_token': 'at', 'refresh_token': refresh, 'expires_at': expires.isoformat()})
        self.integ.save()

    def test_valid_token_used_without_refresh(self):
        with mock.patch('apps.growth.integrations.requests.post') as post, \
                mock.patch('apps.growth.integrations.requests.request', return_value=Resp(200, {'reviews': []})) as req:
            I.gbp_reviews(self.p)
        post.assert_not_called()
        self.assertEqual(req.call_args.kwargs['headers']['Authorization'], 'Bearer at')
        self.assertIn('accounts/1/locations/2/reviews', req.call_args.args[1])

    def test_expired_token_refreshed_and_saved(self):
        self._tokens(expires=timezone.now() - timedelta(minutes=1))
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(200, {'access_token': 'at2', 'expires_in': 3600})), \
                mock.patch('apps.growth.integrations.requests.request', return_value=Resp(200, {'reviews': []})) as req:
            I.gbp_reviews(self.p)
        self.assertEqual(req.call_args.kwargs['headers']['Authorization'], 'Bearer at2')
        self.integ.refresh_from_db()
        self.assertEqual(I.read_secret(self.integ)['access_token'], 'at2')
        self.assertEqual(I.read_secret(self.integ)['refresh_token'], 'rt')

    def test_revoked_refresh_token_marks_error(self):
        self._tokens(expires=timezone.now() - timedelta(minutes=1))
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(400, {'error': 'invalid_grant'})):
            with self.assertRaises(I.IntegrationError):
                I.gbp_reviews(self.p)
        self.integ.refresh_from_db()
        self.assertEqual(self.integ.status, 'error')
        self.assertIn('Connect again', self.integ.last_error)

    def test_missing_refresh_token(self):
        self._tokens(expires=timezone.now() - timedelta(minutes=1), refresh='')
        with self.assertRaises(I.IntegrationError):
            I.gbp_reviews(self.p)

    def test_403_and_429_and_network_errors_are_plain_language(self):
        for resp, text in ((Resp(403, {}), 'refused access'), (Resp(429, {}), 'rate limit'), (Resp(500, {}), r'error \(500\)')):
            with mock.patch('apps.growth.integrations.requests.request', return_value=resp):
                with self.assertRaisesRegex(I.IntegrationError, text):
                    I.gbp_reviews(self.p)
        with mock.patch('apps.growth.integrations.requests.request', side_effect=requests.ConnectionError()):
            with self.assertRaisesRegex(I.IntegrationError, 'Could not reach Google'):
                I.gbp_reviews(self.p)

    def test_reviews_mapping_and_pagination_token(self):
        data = {'reviews': [{'name': 'accounts/1/locations/2/reviews/r1', 'reviewer': {'displayName': 'Sam'}, 'starRating': 'FOUR',
                             'comment': 'Great', 'createTime': '2026-10-01T00:00:00Z', 'reviewReply': {'comment': 'Thanks'}}],
                'averageRating': 4.5, 'totalReviewCount': 12, 'nextPageToken': 'p2'}
        with mock.patch('apps.growth.integrations.requests.request', return_value=Resp(200, data)) as req:
            out = I.gbp_reviews(self.p, page_token='p1')
        self.assertEqual(req.call_args.kwargs['params']['pageToken'], 'p1')
        self.assertEqual(out['reviews'][0]['rating'], 4)
        self.assertEqual((out['next_page_token'], out['total']), ('p2', 12))

    def test_reply_validation_and_request_shape(self):
        for bad in ('', 'x' * 4001):
            with self.assertRaises(I.IntegrationError):
                I.gbp_reply(self.p, 'accounts/1/locations/2/reviews/r1', bad)
        with mock.patch('apps.growth.integrations.requests.request', return_value=Resp(200, {'comment': 'ok'})) as req:
            I.gbp_reply(self.p, 'accounts/1/locations/2/reviews/r1', 'Thank you!')
        self.assertEqual(req.call_args.args[0], 'PUT')
        self.assertTrue(req.call_args.args[1].endswith('/v4/accounts/1/locations/2/reviews/r1/reply'))
        self.assertEqual(req.call_args.kwargs['json'], {'comment': 'Thank you!'})

    def test_reply_needs_selected_location(self):
        self.integ.config = {}
        self.integ.save()
        with self.assertRaisesRegex(I.IntegrationError, 'Choose which'):
            I.gbp_reply(self.p, 'accounts/1/locations/2/reviews/r1', 'Hi')

    def test_post_validation_and_shape(self):
        with self.assertRaises(I.IntegrationError):
            I.gbp_post(self.p, '')
        with mock.patch('apps.growth.integrations.requests.request', return_value=Resp(200, {})) as req:
            I.gbp_post(self.p, 'Open Saturdays', cta_url='https://alpha.test/book')
        body = req.call_args.kwargs['json']
        self.assertEqual((body['topicType'], body['callToAction']['actionType']), ('STANDARD', 'BOOK'))

    def test_location_selection_validates_names(self):
        with self.assertRaises(I.IntegrationError):
            I.gbp_select_location(self.p, 'evil', 'locations/1')
        I.gbp_select_location(self.p, 'accounts/9', 'locations/8', 'New')
        self.integ.refresh_from_db()
        self.assertEqual(self.integ.config['location'], 'locations/8')

    def test_locations_listing(self):
        def fake(method, url, **kw):
            if url.endswith('/accounts'):
                return Resp(200, {'accounts': [{'name': 'accounts/1'}]})
            return Resp(200, {'locations': [{'name': 'locations/2', 'title': 'Alpha', 'phoneNumbers': {'primaryPhone': '919'},
                                             'storefrontAddress': {'addressLines': ['12 Main'], 'postalCode': '27601'}}]})
        with mock.patch('apps.growth.integrations.requests.request', side_effect=fake):
            locs = I.gbp_locations(self.p)
        self.assertEqual(locs[0]['account'], 'accounts/1')
        self.assertEqual(locs[0]['postal_code'], '27601')

    def test_disconnect_revokes_and_clears(self):
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(200, {})) as post:
            I.gbp_disconnect(self.p)
        self.assertIn('revoke', post.call_args.args[0])
        self.integ.refresh_from_db()
        self.assertEqual((self.integ.status, self.integ.secret, self.integ.config), ('not_connected', '', {}))

    def test_oauth_state_expires_and_cannot_be_forged(self):
        import time
        from django.core import signing
        self.assertIsNone(I.gbp_read_state('garbage'))
        old = signing.dumps({'p': '1', 'u': '1', 'n': 'x'}, salt=I.OAUTH_STATE_SALT)
        with mock.patch('time.time', return_value=time.time() + 3600):
            self.assertIsNone(I.gbp_read_state(old))

    def test_code_exchange_failure(self):
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(400, {'error': 'bad'})):
            with self.assertRaises(I.IntegrationError):
                I.gbp_exchange_code(self.p, None, 'code')
        self.integ.refresh_from_db()
        self.assertEqual(self.integ.status, 'error')


class NexHealthTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        self.integ = I.nex_save(self.p, None, 'api-key-1', 'alpha', '42')

    def test_rejected_api_key(self):
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(401, {'error': 'no'})):
            with self.assertRaisesRegex(I.IntegrationError, 'rejected'):
                I.nex_test(self.p)
        self.integ.refresh_from_db()
        self.assertEqual(self.integ.status, 'error')

    def test_token_cached_between_calls(self):
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(200, {'data': {'token': 't1'}})) as post, \
                mock.patch('apps.growth.integrations.requests.get', return_value=Resp(200, {'data': []})):
            I.nex_test(self.p)
            I.nex_test(self.p)
        self.assertEqual(post.call_count, 1)

    def test_slots_request_and_normalisation(self):
        data = {'data': [{'pid': 7, 'next_available_date': '2026-10-14', 'slots': [
            {'time': '2026-10-14T09:00:00.000-04:00', 'end_time': '2026-10-14T09:30:00.000-04:00', 'operatory_id': 3}]}]}
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(200, {'data': {'token': 't'}})), \
                mock.patch('apps.growth.integrations.requests.get', return_value=Resp(200, data)) as get:
            out = I.nex_slots(self.p, '2026-10-14', days=99)
        params = get.call_args.kwargs['params']
        self.assertIn(('subdomain', 'alpha'), params)
        self.assertIn(('lids[]', 42), params)
        self.assertIn(('days', 14), params)
        self.assertEqual(out['slots'][0], {'time': '2026-10-14T09:00:00.000-04:00', 'end_time': '2026-10-14T09:30:00.000-04:00',
                                           'provider_id': 7, 'operatory_id': 3})
        self.assertEqual(out['next_available_date'], '2026-10-14')

    def test_api_errors_and_outage(self):
        with mock.patch('apps.growth.integrations.requests.post', return_value=Resp(200, {'data': {'token': 't'}})), \
                mock.patch('apps.growth.integrations.requests.get', return_value=Resp(503, {})):
            with self.assertRaisesRegex(I.IntegrationError, '503'):
                I.nex_slots(self.p, '2026-10-14')
        self.integ.refresh_from_db()
        I.write_secret(self.integ, {'api_key': 'k'})
        self.integ.save()
        with mock.patch('apps.growth.integrations.requests.post', side_effect=requests.Timeout()):
            with self.assertRaisesRegex(I.IntegrationError, 'Could not reach'):
                I.nex_test(self.p)

    def test_validation_and_disconnect(self):
        with self.assertRaises(I.IntegrationError):
            I.nex_save(self.p, None, 'k', '', '1')
        other = Practice.objects.create(name='B', slug='b', email='b@x.test')
        with self.assertRaisesRegex(I.IntegrationError, 'API key'):
            I.nex_save(other, None, '', 'beta', '1')
        I.nex_disconnect(self.p)
        self.integ.refresh_from_db()
        self.assertEqual((self.integ.status, self.integ.secret), ('not_connected', ''))


@override_settings(SMS_BACKEND='', TWILIO_ACCOUNT_SID='', TWILIO_AUTH_TOKEN='', TWILIO_FROM_NUMBER='', APP_PUBLIC_URL='https://app.test')
class TwilioLiveTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='Alpha', slug='alpha', email='a@x.test')
        Integration.objects.create(practice=self.p, kind='twilio', status='connected', config={'from_number': '+19195550000'},
                                   secret=encrypt_secret(json.dumps({'account_sid': 'AC' + 'a' * 32, 'auth_token': 'tok'})))

    def test_payload_auth_and_status_callback(self):
        from apps.growth.sms import send_sms
        with mock.patch('apps.growth.sms.requests.post', return_value=Resp(201, {'sid': 'SM123'})) as post:
            msg = send_sms(self.p, '(919) 555-0123', 'Hello')
        args, kw = post.call_args
        self.assertTrue(args[0].endswith('/Accounts/AC' + 'a' * 32 + '/Messages.json'))
        self.assertEqual(kw['data']['To'], '+19195550123')
        self.assertEqual(kw['data']['From'], '+19195550000')
        self.assertEqual(kw['data']['StatusCallback'], 'https://app.test/api/v1/growth/sms/status/')
        self.assertEqual(kw['auth'], ('AC' + 'a' * 32, 'tok'))
        self.assertEqual((msg.status, msg.provider_id, msg.provider), ('sent', 'SM123', 'practice'))

    def test_known_error_codes_and_outage(self):
        from apps.growth.sms import SmsError, send_sms
        with mock.patch('apps.growth.sms.requests.post', return_value=Resp(400, {'code': 21610, 'message': 'blocked'})):
            with self.assertRaisesRegex(SmsError, 'replied STOP'):
                send_sms(self.p, '9195550123', 'Hi')
        with mock.patch('apps.growth.sms.requests.post', return_value=Resp(429, {'code': 99999, 'message': 'Too Many Requests'})):
            with self.assertRaisesRegex(SmsError, 'Too Many Requests'):
                send_sms(self.p, '9195550123', 'Hi')
        with mock.patch('apps.growth.sms.requests.post', side_effect=requests.Timeout()):
            with self.assertRaisesRegex(SmsError, 'Could not reach'):
                send_sms(self.p, '9195550123', 'Hi')
        self.assertEqual(SmsMessage.objects.filter(status='failed').count(), 3)

    def test_no_configuration_means_no_send(self):
        from apps.growth.sms import SmsError, send_sms
        other = Practice.objects.create(name='B', slug='b', email='b@x.test')
        with mock.patch('apps.growth.sms.requests.post', side_effect=AssertionError('must not send')):
            with self.assertRaisesRegex(SmsError, 'not set up'):
                send_sms(other, '9195550123', 'Hi')

    def test_twilio_save_checks_credentials(self):
        with mock.patch('apps.growth.integrations.requests.get', return_value=Resp(401, {})):
            with self.assertRaisesRegex(I.IntegrationError, 'rejected'):
                I.twilio_save(self.p, None, 'AC' + 'b' * 32, 't', '+19195550001')
        with self.assertRaisesRegex(I.IntegrationError, 'starts with "AC"'):
            I.twilio_save(self.p, None, 'XX123', 't', '+19195550001')
        with self.assertRaisesRegex(I.IntegrationError, 'sending number'):
            I.twilio_save(self.p, None, 'AC' + 'b' * 32, 't', 'abc')
