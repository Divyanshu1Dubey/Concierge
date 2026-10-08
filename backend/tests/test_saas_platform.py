import io
import zipfile
import json
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.practices.models import Practice, PracticeSettings, BookingRules, EmailProvider, EmailTemplate
from apps.users.models import User
from apps.conversations.models import Conversation, Message
from apps.appointments.models import Appointment
from apps.core.security import encrypt_secret, decrypt_secret, redact_secrets, is_allowed_origin
from apps.conversations.state_machine import ConciergeStateMachine


class TestHeyJarvisSaaSPlatform(TestCase):
    """Comprehensive test suite for HeyJarvis Concierge Cloud SaaS Platform."""

    def setUp(self):
        self.client = APIClient()

        # Create Tenant A (Raleigh Dentistry)
        self.practice_a = Practice.objects.create(
            name="Raleigh Dentistry",
            slug="raleigh-dentistry",
            email="frontdesk@raleighdentistry.com",
            phone="919-555-0100",
            api_key="client_key_tenant_a_12345"
        )
        self.user_a = User.objects.create_user(
            username="admin@raleighdentistry.com",
            email="admin@raleighdentistry.com",
            password="Password123!",
            first_name="Admin",
            last_name="User",
            role="owner",
            practice=self.practice_a
        )
        self.token_a = str(RefreshToken.for_user(self.user_a).access_token)

        # Create Tenant B (Charlotte Smiles)
        self.practice_b = Practice.objects.create(
            name="Charlotte Smiles",
            slug="charlotte-smiles",
            email="contact@charlottesmiles.com",
            phone="704-555-0200",
            api_key="client_key_tenant_b_67890"
        )
        self.user_b = User.objects.create_user(
            username="owner@charlottesmiles.com",
            email="owner@charlottesmiles.com",
            password="Password123!",
            first_name="Owner",
            last_name="B",
            role="owner",
            practice=self.practice_b
        )
        self.token_b = str(RefreshToken.for_user(self.user_b).access_token)

        # Seed data for Tenant A
        self.conv_a = Conversation.objects.create(
            practice=self.practice_a,
            patient_name="Sarah Jenkins",
            patient_email="sarah@example.com",
            patient_phone="919-555-0142",
            state="CONFIRMING",
            status="active",
            urgency="normal"
        )
        self.appt_a = Appointment.objects.create(
            practice=self.practice_a,
            patient_name="Sarah Jenkins",
            patient_email="sarah@example.com",
            patient_phone="919-555-0142",
            service_name="Cleaning",
            intent="cleaning",
            urgency="normal",
            status="pending"
        )

        # Seed data for Tenant B
        self.conv_b = Conversation.objects.create(
            practice=self.practice_b,
            patient_name="Bob Miller",
            patient_email="bob@example.com",
            state="STARTED",
            status="active"
        )

    # 1. Health & Infrastructure
    def test_health_and_readiness_endpoints(self):
        resp = self.client.get("/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("version", data)

        resp = self.client.get("/ready/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

        resp = self.client.get("/version/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("version", resp.json())

    # 2. Universal Widget Serving
    def test_serve_widget_js(self):
        resp = self.client.get("/widget.js")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/javascript")
        self.assertIn("heyjarvis", resp.content.decode("utf-8").lower())

    # 3. Security & AES-256 Encryption
    def test_aes_encryption_and_redaction(self):
        secret = "SuperSecretSmtpPass!#9"
        encrypted = encrypt_secret(secret)
        self.assertNotEqual(secret, encrypted)
        decrypted = decrypt_secret(encrypted)
        self.assertEqual(secret, decrypted)

        # Redaction check
        data = {"api_key": "12345", "password": "pass", "smtp_password": "smtp", "name": "Safe"}
        redacted = redact_secrets(data)
        self.assertEqual(redacted["password"], "[REDACTED]")
        self.assertEqual(redacted["smtp_password"], "[REDACTED]")
        self.assertEqual(redacted["name"], "Safe")

    # 4. Public Widget Endpoints
    def test_public_widget_config_and_hosted_concierge(self):
        # Valid client key
        resp = self.client.get(f"/api/v1/widget/config/?client_key={self.practice_a.client_key}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["practice_name"], "Raleigh Dentistry")
        self.assertIn("primary_color", data)

        # Invalid client key
        resp = self.client.get("/api/v1/widget/config/?client_key=invalid_key")
        self.assertEqual(resp.status_code, 404)

        # Hosted concierge by slug
        resp = self.client.get(f"/api/v1/concierge/{self.practice_a.slug}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["practice_name"], "Raleigh Dentistry")

    # 5. Concierge State Machine & Entity Extraction
    def test_state_machine_natural_language_extraction(self):
        conv = Conversation.objects.create(practice=self.practice_a)
        sm = ConciergeStateMachine(conversation=conv, practice=self.practice_a)

        # Message with natural language intent, date, and time
        result = sm.process_message("Hi, I'm John. I need a cleaning Thursday afternoon.")
        self.assertEqual(conv.patient_name, "John")
        self.assertEqual(conv.intent, "cleaning")
        self.assertIn("thursday", conv.preferred_date.lower())
        self.assertIn("afternoon", conv.preferred_time.lower())

        # Emergency intent triage without medical advice
        conv_em = Conversation.objects.create(practice=self.practice_a)
        sm_em = ConciergeStateMachine(conversation=conv_em, practice=self.practice_a)
        res_em = sm_em.process_message("I have severe pain and bleeding!")
        self.assertEqual(conv_em.urgency, "URGENT")
        self.assertEqual(conv_em.intent, "emergency")
        # Should not invent medical prescriptions
        self.assertNotIn("prescribe", res_em["message"].lower())
        self.assertIn("emergency", res_em["message"].lower())

    # 6. Tenant Isolation: Data Scoping
    def test_tenant_isolation_conversations_and_requests(self):
        # User A requests list
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")
        resp_a = self.client.get("/api/requests/")
        self.assertEqual(resp_a.status_code, 200)
        ids_a = [r["id"] for r in resp_a.json()]
        self.assertIn(str(self.appt_a.id), ids_a)

        # User B requests list (Must NOT see Tenant A's appointment)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_b}")
        resp_b = self.client.get("/api/requests/")
        self.assertEqual(resp_b.status_code, 200)
        ids_b = [r["id"] for r in resp_b.json()]
        self.assertNotIn(str(self.appt_a.id), ids_b)

        # User B cannot access Tenant A's appointment detail
        resp_cross = self.client.get(f"/api/requests/{self.appt_a.id}/")
        self.assertEqual(resp_cross.status_code, 404)

    # 7. Front Desk AI Draft, Notes, and Reply
    def test_front_desk_ai_draft_and_response(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")

        # Generate AI draft
        resp = self.client.post(
            f"/api/requests/{self.appt_a.id}/ai-draft/",
            {"action": "draft"},
            format="json"
        )
        self.assertEqual(resp.status_code, 200)
        draft = resp.json()["draft"]
        self.assertIn("Sarah", draft)

        # Add staff internal note
        resp_note = self.client.post(
            f"/api/requests/{self.appt_a.id}/notes/",
            {"text": "Patient has Delta Dental PPO insurance."},
            format="json"
        )
        self.assertEqual(resp_note.status_code, 200)
        self.appt_a.refresh_from_db()
        self.assertIn("Delta Dental", str(self.appt_a.internal_notes))

        # Send Reply
        resp_send = self.client.post(
            f"/api/requests/{self.appt_a.id}/send-reply/",
            {
                "to_email": "sarah@example.com",
                "subject": "Regarding your cleaning",
                "body": draft
            },
            format="json"
        )
        self.assertEqual(resp_send.status_code, 200)
        self.appt_a.refresh_from_db()
        self.assertEqual(self.appt_a.status, "contacted")
        self.assertIsNotNone(self.appt_a.response_sent_at)

    # 8. WordPress Plugin Dynamic ZIP Download
    def test_wordpress_plugin_download(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")
        resp = self.client.get("/api/practices/integration/wordpress/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")

        # Verify ZIP contains valid plugin and client key
        zip_buffer = io.BytesIO(resp.content)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            namelist = zf.namelist()
            self.assertIn("heyjarvis-concierge/heyjarvis-concierge.php", namelist)
            main_php = zf.read("heyjarvis-concierge/heyjarvis-concierge.php").decode("utf-8")
            self.assertIn(self.practice_a.client_key, main_php)
            self.assertIn("widget.js", main_php)

    # 9. Client Key Regeneration
    def test_client_key_regeneration(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")
        old_key = self.practice_a.client_key

        resp = self.client.post("/api/practices/key/regenerate/")
        self.assertEqual(resp.status_code, 200)
        new_key = resp.json()["client_key"]
        self.assertNotEqual(old_key, new_key)

        # Old key is invalidated
        resp_old = self.client.get(f"/api/v1/widget/config/?client_key={old_key}")
        self.assertEqual(resp_old.status_code, 404)

        # New key succeeds
        resp_new = self.client.get(f"/api/v1/widget/config/?client_key={new_key}")
        self.assertEqual(resp_new.status_code, 200)

    # 10. Real Metrics & CSV Exports
    def test_metrics_and_csv_export(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token_a}")

        # Real metrics endpoint
        resp_m = self.client.get("/api/practices/metrics/")
        self.assertEqual(resp_m.status_code, 200)
        m = resp_m.json()
        self.assertEqual(m["conversations"], 1)
        self.assertEqual(m["system_status"], "operational")

        # CSV Export for Leads
        resp_leads = self.client.get("/api/practices/export/leads/")
        self.assertEqual(resp_leads.status_code, 200)
        self.assertEqual(resp_leads["Content-Type"], "text/csv")
        content_leads = resp_leads.content.decode("utf-8")
        self.assertIn("Sarah Jenkins", content_leads)

        # CSV Export for Conversations
        resp_convs = self.client.get("/api/practices/export/conversations/")
        self.assertEqual(resp_convs.status_code, 200)
        self.assertEqual(resp_convs["Content-Type"], "text/csv")
        content_convs = resp_convs.content.decode("utf-8")
        self.assertIn("Sarah Jenkins", content_convs)
