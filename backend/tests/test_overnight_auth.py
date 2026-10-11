"""Overnight QA: token edge cases and CSV import abuse cases."""
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.growth.models import RecallContact
from apps.practices.models import Practice
from apps.users.models import User

URL = '/api/v1/growth/recall/'


class TokenEdgeTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        self.u = User.objects.create_user(username='u@x.test', email='u@x.test', password='Str0ng-Test-Passphrase-91',
                                          role='PRACTICE_ADMIN', practice=self.p)

    def call(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        return c.get(URL)

    def test_valid_token_works(self):
        self.assertEqual(self.call(AccessToken.for_user(self.u)).status_code, 200)

    def test_expired_token_rejected(self):
        t = AccessToken.for_user(self.u)
        t.set_exp(lifetime=-timedelta(seconds=1))
        self.assertEqual(self.call(t).status_code, 401)

    def test_tampered_and_malformed_tokens_rejected(self):
        t = str(AccessToken.for_user(self.u))
        head, body, sig = t.split('.')
        for bad in (head + '.' + body + '.' + sig[::-1], 'not.a.jwt', '', 'Bearer', t + 'x'):
            self.assertEqual(self.call(bad).status_code, 401, bad[:20])

    def test_deactivated_user_token_rejected(self):
        t = AccessToken.for_user(self.u)
        self.u.is_active = False
        self.u.save()
        self.assertEqual(self.call(t).status_code, 401)

    def test_refresh_token_cannot_be_used_as_access_token(self):
        self.assertEqual(self.call(RefreshToken.for_user(self.u)).status_code, 401)

    def test_rotated_refresh_token_cannot_be_reused(self):
        r = RefreshToken.for_user(self.u)
        first = APIClient().post('/api/auth/token/refresh/', {'refresh': str(r)}, format='json')
        self.assertEqual(first.status_code, 200)
        again = APIClient().post('/api/auth/token/refresh/', {'refresh': str(r)}, format='json')
        self.assertEqual(again.status_code, 401)

    def test_user_moved_out_of_practice_loses_access(self):
        t = AccessToken.for_user(self.u)
        RecallContact.objects.create(practice=self.p, name='Secret Patient', email='s@x.test')
        self.u.practice = None
        self.u.save()
        r = self.call(t)
        self.assertNotIn(b'Secret Patient', r.content)


class CsvAbuseTests(TestCase):
    def setUp(self):
        self.p = Practice.objects.create(name='A', slug='a', email='a@x.test')
        u = User.objects.create_user(username='u@x.test', email='u@x.test', password='Str0ng-Test-Passphrase-91',
                                     role='PRACTICE_ADMIN', practice=self.p)
        self.c = APIClient()
        self.c.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(u)}')

    def upload(self, content: bytes, name='list.csv'):
        return self.c.post('/api/v1/growth/recall/import/', {'file': SimpleUploadedFile(name, content, 'text/csv')}, format='multipart')

    def test_missing_file_and_empty_file(self):
        self.assertEqual(self.c.post('/api/v1/growth/recall/import/', {}, format='multipart').status_code, 400)
        self.assertIn('empty', self.upload(b'').json()['errors'][0])

    def test_oversized_file_rejected_before_parsing(self):
        r = self.upload(b'name,email\n' + b'x,y@z.test\n' * 400000)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(RecallContact.objects.count(), 0)

    def test_binary_garbage_does_not_crash(self):
        r = self.upload(bytes(range(256)) * 50)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(RecallContact.objects.count(), 0)

    def test_bom_and_latin1_files(self):
        r = self.upload('﻿Name,Email\nJosé Núñez,jose@x.test\n'.encode('utf-8'))
        self.assertEqual(r.json()['created'], 1)
        r = self.upload('Name,Email\nFrançois,francois@x.test\n'.encode('latin-1'))
        self.assertEqual(r.json()['created'], 1)
        self.assertTrue(RecallContact.objects.filter(name='François').exists())

    def test_row_cap(self):
        from apps.growth import outreach
        with mock.patch.object(outreach, 'MAX_IMPORT_ROWS', 5):
            rows = ''.join(f'P{i},p{i}@x.test\n' for i in range(10))
            r = self.upload(('name,email\n' + rows).encode())
        self.assertEqual(r.json()['created'], 5)
        self.assertTrue(any('Stopped after 5 rows' in e for e in r.json()['errors']))

    def test_formula_like_names_stored_as_text_not_executed(self):
        self.upload(b'name,email\n=HYPERLINK("http://evil"),f@x.test\n')
        self.assertEqual(RecallContact.objects.get().name, '=HYPERLINK("http://evil")')

    def test_missing_required_columns(self):
        self.assertIn('"name"', self.upload(b'email\na@x.test\n').json()['errors'][0])
        self.assertIn('email', self.upload(b'name\nAna\n').json()['errors'][0])
