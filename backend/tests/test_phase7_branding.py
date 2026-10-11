"""Phase 7: practice branding - logo/team uploads, branded emails, widget brand, isolation."""
import io

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.practices.models import BrandAsset, BookingRules, Practice, PracticeDoctor, PracticeSettings
from apps.users.models import User

PW = 'Str0ng-Test-Passphrase-91'


def make_user(email, role, practice):
    return User.objects.create_user(username=email, email=email, password=PW, role=role, practice=practice)


def client_for(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


def png(w=1200, h=400, color=(20, 90, 70, 255), name='logo.png'):
    buf = io.BytesIO()
    Image.new('RGBA', (w, h), color).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


@override_settings(APP_PUBLIC_URL='https://concierge.example')
class BrandingTests(TestCase):
    def setUp(self):
        self.a = Practice.objects.create(name='Alpha Smiles', slug='alpha', email='front@alpha.test', phone='(919) 555-0100',
                                         address='1 Main St', city='Raleigh', state='NC', zip_code='27601')
        self.b = Practice.objects.create(name='Beta Dental', slug='beta', email='b@beta.test')
        for p in (self.a, self.b):
            BookingRules.objects.get_or_create(practice=p)
            PracticeSettings.objects.get_or_create(practice=p)
        self.doc = make_user('doc@alpha.test', 'PRACTICE_ADMIN', self.a)
        self.desk = make_user('desk@alpha.test', 'FRONT_DESK', self.a)
        self.doc_b = make_user('doc@beta.test', 'PRACTICE_ADMIN', self.b)

    def test_staff_team_route_is_still_staff_management(self):
        res = client_for(self.doc).get('/api/practices/team/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('desk@alpha.test', res.content.decode())

    def test_logo_upload_is_optimized_served_and_replaced(self):
        res = client_for(self.doc).post('/api/practices/branding/logo/', {'file': png()}, format='multipart')
        self.assertEqual(res.status_code, 201, res.content)
        url = res.json()['logo_url']
        self.assertTrue(url.startswith('https://concierge.example/api/v1/brand-assets/'))
        asset = BrandAsset.objects.get(practice=self.a, kind='logo')
        self.assertLessEqual(asset.width, 480)
        self.assertLessEqual(asset.height, 160)
        served = APIClient().get(url.replace('https://concierge.example', ''))
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served['Content-Type'], 'image/png')
        self.assertIn('immutable', served['Cache-Control'])
        client_for(self.doc).post('/api/practices/branding/logo/', {'file': png(color=(200, 0, 0, 255))}, format='multipart')
        self.assertEqual(BrandAsset.objects.filter(practice=self.a, kind='logo').count(), 1)
        self.assertEqual(APIClient().get(url.replace('https://concierge.example', '')).status_code, 404)
        client_for(self.doc).delete('/api/practices/branding/logo/')
        self.a.refresh_from_db()
        self.assertEqual(self.a.logo_url, '')

    def test_invalid_uploads_are_rejected(self):
        c = client_for(self.doc)
        bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        self.assertEqual(c.post('/api/practices/branding/logo/', {'file': bad}, format='multipart').status_code, 400)
        svg = SimpleUploadedFile('x.svg', b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"></svg>', content_type='image/svg+xml')
        res = c.post('/api/practices/branding/logo/', {'file': svg}, format='multipart')
        self.assertEqual(res.status_code, 400)
        self.assertIn('PNG', res.json()['error'])
        self.assertEqual(c.post('/api/practices/branding/logo/', {}, format='multipart').status_code, 400)
        self.assertFalse(BrandAsset.objects.exists())

    def test_permissions_and_isolation(self):
        self.assertEqual(client_for(self.desk).post('/api/practices/branding/logo/', {'file': png()}, format='multipart').status_code, 403)
        self.assertEqual(client_for(self.desk).patch('/api/practices/branding/', {'tagline': 'x'}, format='json').status_code, 403)
        doc_id = client_for(self.doc).post('/api/practices/branding/team/', {'name': 'Dr. Ana Lee'}, format='json').json()['id']
        self.assertEqual(client_for(self.doc_b).patch(f'/api/practices/branding/team/{doc_id}/', {'name': 'Hacked'}, format='json').status_code, 404)
        self.assertEqual(client_for(self.doc_b).post(f'/api/practices/branding/team/{doc_id}/photo/', {'file': png()}, format='multipart').status_code, 404)
        self.assertEqual(client_for(self.doc_b).get('/api/practices/branding/').json()['doctors'], [])
        self.assertEqual(PracticeDoctor.objects.get(pk=doc_id).name, 'Dr. Ana Lee')

    def test_links_are_validated(self):
        res = client_for(self.doc).patch('/api/practices/branding/', {'social_links': {'instagram': 'javascript:alert(1)'}}, format='json')
        self.assertEqual(res.status_code, 400)
        res = client_for(self.doc).patch('/api/practices/branding/', {'tagline': 'Gentle family dentistry',
                                                                     'social_links': {'instagram': 'instagram.com/alphasmiles'}}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['social_links']['instagram'], 'https://instagram.com/alphasmiles')

    def test_team_photo_is_square_and_reaches_widget_and_ai(self):
        c = client_for(self.doc)
        doc_id = c.post('/api/practices/branding/team/', {'name': 'Dr. Ana Lee', 'credentials': 'DDS', 'bio': 'Gentle with nervous patients.'}, format='json').json()['id']
        res = c.post(f'/api/practices/branding/team/{doc_id}/photo/', {'file': png(800, 500, (180, 160, 140, 255), 'p.png')}, format='multipart')
        self.assertEqual(res.status_code, 200, res.content)
        photo = BrandAsset.objects.get(kind='photo')
        self.assertEqual((photo.width, photo.height, photo.content_type), (320, 320, 'image/jpeg'))
        cfg = APIClient().get(f'/api/v1/widget/config/?client_key={self.a.api_key}').json()
        self.assertEqual(cfg['team'][0]['name'], 'Dr. Ana Lee')
        self.assertTrue(cfg['team'][0]['photo_url'].endswith('.jpg'))
        self.assertNotIn('bio', cfg['team'][0])
        from apps.ai_service.engine import build_practice_facts
        self.assertIn('Dr. Ana Lee (DDS) - Gentle with nervous patients.', build_practice_facts(Practice.objects.get(pk=self.a.pk)))
        other = APIClient().get(f'/api/v1/widget/config/?client_key={self.b.api_key}').json()
        self.assertEqual(other['team'], [])

    def test_suspended_practice_assets_are_not_served(self):
        url = client_for(self.doc).post('/api/practices/branding/logo/', {'file': png()}, format='multipart').json()['logo_url']
        Practice.objects.filter(pk=self.a.pk).update(active=False)
        self.assertEqual(APIClient().get(url.replace('https://concierge.example', '')).status_code, 404)

    def test_staff_reply_uses_branded_layout_with_escaping(self):
        c = client_for(self.doc)
        c.post('/api/practices/branding/logo/', {'file': png()}, format='multipart')
        c.patch('/api/practices/branding/', {'tagline': 'Gentle family dentistry', 'social_links': {'google_reviews': 'https://g.page/r/alpha'}}, format='json')
        appt = Appointment.objects.create(practice=self.a, patient_name='Pat', patient_email='pat@example.test', intent='cleaning')
        res = client_for(self.desk).post(f'/api/requests/{appt.id}/send-reply/', {
            'to_email': 'pat@example.test', 'subject': 'Hello', 'body': 'Hi Pat,\n<b>See you soon</b>'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        msg = mail.outbox[-1]
        self.assertEqual(msg.body, 'Hi Pat,\n<b>See you soon</b>')
        html = msg.alternatives[0][0]
        self.assertIn('/api/v1/brand-assets/', html)
        self.assertIn('Gentle family dentistry', html)
        self.assertIn('https://g.page/r/alpha', html)
        self.assertIn('&lt;b&gt;See you soon&lt;/b&gt;', html)

    def test_unbranded_practice_gets_a_clean_default(self):
        from apps.emails.branded import render_branded_message
        html = render_branded_message(Practice.objects.get(pk=self.b.pk), 'Hello')
        self.assertIn('Beta Dental', html)
        self.assertNotIn('<img', html)
        self.assertIn('>B<', html)  # initial badge instead of a broken image
        preview = client_for(self.doc_b).post('/api/practices/branding/email-preview/', {}, format='json')
        self.assertEqual(preview.status_code, 200)
        self.assertIn('Beta Dental', preview.json()['html'])