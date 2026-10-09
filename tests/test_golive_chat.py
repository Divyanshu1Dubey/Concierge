"""Go-live checks for the patient chat: privacy, one lead per request, emergencies, names, rate limits."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from saas import cadence
from saas.conversation import ConversationContext, ConversationEngine, _rule_fields
from saas.database import connect, rows
from saas.repositories import create_api_key, create_tenant, create_user, save_clinic_profile

CHAT = "/api/v1/public/conversations"


@pytest.fixture
def client():
    from saas.main import app
    return TestClient(app)


@pytest.fixture
def clinic():
    t = create_tenant(slug=f"gl-{uuid.uuid4().hex[:6]}", name="Golive Dental")
    create_user(t.id, "owner@gl.test", password="pw-123456", role="owner")
    return {"id": t.id, "slug": t.slug, "key": create_api_key(t.id, "w", "s").public_key}


class Chat:
    """One patient's browser: starts a chat and sends messages with its own token."""

    def __init__(self, client, key):
        self.client, self.key = client, key
        start = client.post(CHAT, params={"client_key": key}).json()
        self.id, self.token = start["conversation_id"], start["conversation_token"]

    def send(self, message, token=None):
        return self.client.post(f"{CHAT}/{self.id}/messages", params={"client_key": self.key},
                                json={"message": message},
                                headers={"X-Conversation-Token": self.token if token is None else token})

    def say(self, *messages):
        out = None
        for m in messages:
            r = self.send(m)
            assert r.status_code == 200, r.text
            out = r.json()
        return out


def _leads(tenant_id):
    with connect() as c:
        return rows(c, "SELECT * FROM leads WHERE tenant_id = ?", tenant_id)


# ── 1. One patient's chat is not readable or writable by another visitor ─────


def test_messages_need_the_chat_token_not_just_the_public_key(client, clinic):
    chat = Chat(client, clinic["key"])
    assert len(chat.token) >= 32
    for bad in ("", "wrong-token", Chat(client, clinic["key"]).token):  # none, guessed, another patient's
        r = chat.send("what did I tell you?", token=bad)
        assert r.status_code == 404
    assert chat.send("Hi").status_code == 200


def test_missing_token_header_is_404(client, clinic):
    chat = Chat(client, clinic["key"])
    r = client.post(f"{CHAT}/{chat.id}/messages", params={"client_key": clinic["key"]}, json={"message": "hi"})
    assert r.status_code == 404


def test_only_a_hash_of_the_token_is_stored(client, clinic):
    chat = Chat(client, clinic["key"])
    with connect() as c:
        stored = rows(c, "SELECT access_token FROM conversations WHERE id = ?", chat.id)[0]["access_token"]
    assert stored and chat.token not in stored


def test_chats_started_before_tokens_are_closed(client, clinic):
    from saas.repositories import create_conversation
    old = create_conversation(clinic["id"])  # no token on record
    r = client.post(f"{CHAT}/{old['id']}/messages", params={"client_key": clinic["key"]}, json={"message": "hi"},
                    headers={"X-Conversation-Token": ""})
    assert r.status_code == 404


def test_widget_and_hosted_page_send_the_token():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src" / "saas" / "static" / "widget.js").read_text()
    assert src.count("conversationToken = data.conversation_token") == 2  # hosted and embedded
    assert src.count("token: conversationToken") == 2
    assert src.count("headers['X-Conversation-Token']") == 2


# ── 2. One lead per request ───────────────────────────────────────────────────


def test_messages_after_submit_do_not_create_another_lead(client, clinic, monkeypatch):
    from saas import public_api
    alerts = []
    monkeypatch.setattr(public_api, "_alert_team_new_lead", lambda tid, lid: alerts.append(lid))
    chat = Chat(client, clinic["key"])
    out = chat.say("Checkup & cleaning", "Sam Lee", "sam@x.test")
    assert out["state"] == "submitted"
    [lead] = _leads(clinic["id"])
    assert cadence.get_enrollment(clinic["id"], lead["id"])["status"] == "active"

    out = chat.say("Oh, and can you also check my crown?")
    assert out["state"] == "submitted" and "already has your request" in out["reply"]
    chat.say("Also I'm Sam Lee, sam@x.test, I need a cleaning")
    assert len(_leads(clinic["id"])) == 1 and alerts == [lead["id"]]
    with connect() as c:
        enrolled = rows(c, "SELECT COUNT(*) n FROM cadence_enrollments WHERE tenant_id = ?", clinic["id"])[0]["n"]
        said = [m["body"] for m in rows(c, "SELECT body FROM messages WHERE conversation_id = ? AND role = 'user'",
                                        chat.id)]
    assert enrolled == 1
    assert "Oh, and can you also check my crown?" in said  # kept with the request staff already have


def test_a_new_request_is_a_new_conversation(client, clinic):
    Chat(client, clinic["key"]).say("Implants", "Sam Lee", "sam@x.test")
    Chat(client, clinic["key"]).say("Checkup & cleaning", "Sam Lee", "sam@x.test")
    assert len(_leads(clinic["id"])) == 2


def test_only_one_of_two_racing_submits_creates_the_lead(client, clinic):
    from saas.public_api import _claim_lead_slot
    chat = Chat(client, clinic["key"])
    assert _claim_lead_slot(chat.id) is True
    assert _claim_lead_slot(chat.id) is False


def test_emergency_follow_up_after_submit_repeats_call_now(client, clinic):
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100"})
    chat = Chat(client, clinic["key"])
    assert chat.say("Emergency", "Mike Chang", "mike@x.test", "skip")["state"] == "submitted"
    out = chat.say("it's getting worse")
    assert "already has your request" in out["reply"] and "(919) 555-0100" in out["reply"]
    assert len(_leads(clinic["id"])) == 1


# ── 3. Emergencies ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["I have a toothache", "bad tooth ache", "it hurts", "my jaw is hurting",
                                  "pain on the left", "it's painful", "broken tooth", "cracked molar",
                                  "chipped my front tooth", "tooth got knocked out", "swelling in my cheek",
                                  "my gum is swollen", "bleeding gums", "I think it's an abscess",
                                  "I have an infection", "I can't sleep", "I cant sleep", "I can\u2019t sleep",
                                  "severe", "this is urgent", "Emergency"])
def test_emergency_words(text):
    assert _rule_fields(text, None).get("intent") == "emergency"


@pytest.mark.parametrize("text", ["I live in Spain", "unbroken record", "paint color", "I want whitening"])
def test_emergency_words_match_whole_words_only(text):
    assert _rule_fields(text, None).get("intent") != "emergency"


def test_email_addresses_are_ignored_for_keywords():
    out = _rule_fields("reach me at pain.exam@example.com", "email")
    assert out["email"] == "pain.exam@example.com"
    assert "intent" not in out and "service" not in out
    assert "intent" not in _rule_fields("it's urgent.care@example.com", None)


def test_emergency_is_never_downgraded():
    eng = ConversationEngine({})
    ctx = ConversationContext(conversation_id=0, tenant_id=0)
    ctx.fields.update(eng._extract_fields("my tooth is broken", ctx.fields))
    assert ctx.fields["intent"] == "emergency"
    ctx.fields.update(eng._extract_fields("also I'd like a cleaning appointment, new patient", ctx.fields))
    assert ctx.fields["intent"] == "emergency"


def test_emergency_is_never_downgraded_over_the_api(client, clinic):
    chat = Chat(client, clinic["key"])
    chat.say("my tooth is cracked", "Ana Ruiz", "I'd also like a cleaning appointment, ana@x.test", "no")
    [lead] = _leads(clinic["id"])
    assert lead["intent"] == "emergency"


def test_ai_reading_cannot_hide_an_emergency(monkeypatch):
    from saas import ai_engine
    monkeypatch.setattr(ai_engine, "extract_intake", lambda *a: {"intent": "appointment_request"})
    eng = ConversationEngine({})
    assert eng._extract_fields("my crown broke and it hurts", {})["intent"] == "emergency"


def test_first_emergency_reply_says_call_the_clinic_before_asking_name(client, clinic):
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100"})
    out = Chat(client, clinic["key"]).say("my tooth is killing me, severe pain")
    reply = out["reply"]
    assert "(919) 555-0100" in reply and "name" in reply.lower()
    assert reply.index("(919) 555-0100") < reply.lower().index("name")
    tapped = Chat(client, clinic["key"]).say("Emergency")["reply"]
    assert "(919) 555-0100" in tapped and "name" in tapped.lower()


def test_first_emergency_reply_without_clinic_phone(client, clinic):
    reply = Chat(client, clinic["key"]).say("Emergency")["reply"]
    assert "please call our office now" in reply


def test_call_now_is_said_once_not_every_turn(client, clinic):
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100"})
    chat = Chat(client, clinic["key"])
    chat.say("Emergency")
    out = chat.say("Mike Chang")
    assert "(919) 555-0100" not in out["reply"] and "email" in out["reply"].lower()


@pytest.mark.parametrize("skip", ["skip", "no", "No thanks", "nope", "just email me", "I'd rather not"])
def test_emergency_asks_for_callback_number_and_it_can_be_skipped(client, clinic, skip):
    chat = Chat(client, clinic["key"])
    out = chat.say("Emergency", "Mike Chang", "mike@x.test")
    assert out["state"] != "submitted" and "phone number" in out["reply"] and "skip" in out["reply"]
    out = chat.say(skip)
    assert out["state"] == "submitted"
    [lead] = _leads(clinic["id"])
    assert lead["intent"] == "emergency" and not lead["phone"]


def test_emergency_callback_number_is_saved(client, clinic):
    chat = Chat(client, clinic["key"])
    out = chat.say("Emergency", "Mike Chang", "mike@x.test", "919-555-0123")
    assert out["state"] == "submitted"
    assert _leads(clinic["id"])[0]["phone"] == "919-555-0123"


def test_unclear_callback_answer_asks_again(client, clinic):
    chat = Chat(client, clinic["key"])
    chat.say("Emergency", "Mike Chang", "mike@x.test")
    out = chat.say("it really hurts")
    assert out["state"] != "submitted" and "skip" in out["reply"]


def test_non_emergency_does_not_ask_for_phone(client, clinic):
    out = Chat(client, clinic["key"]).say("Implants", "Sam Lee", "sam@x.test")
    assert out["state"] == "submitted"


# ── 4. Names ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("reply", ["sure", "ok", "Yes", "no", "hi", "Hi there", "I want veneers", "thanks!"])
def test_non_names_are_not_taken_as_names(client, clinic, reply):
    chat = Chat(client, clinic["key"])
    chat.say("Implants")
    out = chat.say(reply)
    assert "name" not in out["fields"]
    assert "didn't catch your name" in out["reply"]
    out = chat.say("Sam Lee")
    assert out["fields"]["name"] == "Sam Lee" and "email" in out["reply"].lower()


@pytest.mark.parametrize("name", ["Mary Ann De La Cruz", "José Núñez", "Lily An", "O'Neil", "Will Grace",
                                  "Test Patient"])
def test_real_names_are_accepted(client, clinic, name):
    out = Chat(client, clinic["key"]).say("Implants", name)
    assert out["fields"]["name"] == name and "email" in out["reply"].lower()


def test_name_with_email_in_same_answer(client, clinic):
    out = Chat(client, clinic["key"]).say("Implants", "Sarah, sarah@x.test")
    assert out["state"] == "submitted" and out["fields"]["name"] == "Sarah"


def test_hurting_is_not_a_name():
    assert "name" not in _rule_fields("I'm hurting a lot", None)


# ── 5. Rate limits key on the address our proxy saw ──────────────────────────


def _req(xff=None, host="10.0.0.1"):
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


def test_client_ip_is_rightmost_forwarded_entry():
    from saas.public_api import _client_ip
    assert _client_ip(_req("6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    assert _client_ip(_req("203.0.113.9:4431")) == "203.0.113.9"
    assert _client_ip(_req("1.2.3.4, [2001:db8::1]:443")) == "2001:db8::1"
    assert _client_ip(_req("2001:db8::2")) == "2001:db8::2"
    assert _client_ip(_req()) == "10.0.0.1"


def test_spoofed_forwarded_for_does_not_bypass_the_limit():
    """As deployed: uvicorn --proxy-headers --forwarded-allow-ips '*' sets request.client to the LEFTMOST entry."""
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

    from saas.main import app
    t = create_tenant(slug=f"rl-{uuid.uuid4().hex[:6]}", name="RL")
    key = create_api_key(t.id, "w", "s").public_key
    proxied = TestClient(ProxyHeadersMiddleware(app, trusted_hosts="*"))
    codes = [proxied.post(CHAT, params={"client_key": key},
                          headers={"X-Forwarded-For": f"10.9.{i}.1, 198.51.100.7"}).status_code for i in range(22)]
    assert codes[:20] == [200] * 20 and codes[20:] == [429, 429]
    other = proxied.post(CHAT, params={"client_key": key}, headers={"X-Forwarded-For": "10.9.0.1, 198.51.100.8"})
    assert other.status_code == 200  # a different real visitor is not blocked


# ── 6. Public config carries only what the widget shows ──────────────────────


def test_public_config_hides_internal_settings(client, clinic):
    save_clinic_profile(clinic["id"], {"phone": "(919) 555-0100", "address": "1 Main St"})
    with connect() as c:
        flags = json.loads(rows(c, "SELECT flags FROM tenant_settings WHERE tenant_id = ?", clinic["id"])[0]["flags"])
        flags.update({"greeting": "Welcome!", "ai_enabled": True, "max_turns": 9, "lead_collection_enabled": True,
                      "service_options": ["Botox", "Fillers"], "custom_fields": [{"key": "ssn"}]})
        c.execute("UPDATE tenant_settings SET flags = ?, ai_instructions = ? WHERE tenant_id = ?",
                  (json.dumps(flags), "SECRET internal prompt", clinic["id"]))
        c.execute("INSERT INTO widget_settings (tenant_id, config, updated_at) VALUES (?, ?, ?)",
                  (clinic["id"], json.dumps({"primary_color": "#123456", "title": "Chat", "max_turns": 9}), "x"))
    cfg = client.get("/api/v1/public/config", params={"client_key": clinic["key"]}).json()
    wc = cfg["widget_config"]
    assert wc == {"title": "Chat", "primary_color": "#123456", "greeting": "Welcome!",
                  "service_options": ["Botox", "Fillers"], "clinic": {"phone": "(919) 555-0100"}}
    assert cfg["tenant_name"] == "Golive Dental" and cfg["greeting"] == "Welcome!"
    assert "SECRET" not in json.dumps(cfg)


# ── 7. Staff alert carries no patient details ────────────────────────────────


def test_new_request_alert_from_chat_has_no_patient_details(client, clinic, monkeypatch):
    from saas import login_codes
    sent = []
    monkeypatch.setattr(login_codes, "send_system_email",
                        lambda to, subject, body, dev_note=None: sent.append((subject, body)) or True)
    assert Chat(client, clinic["key"]).say("Root canal please", "Dana Cruz", "dana@x.test")["state"] == "submitted"
    [(subject, body)] = sent
    assert subject == "New patient request" and f"/frontdesk?clinic={clinic['slug']}" in body
    for private in ("Dana", "Cruz", "dana@x.test", "root canal", "Root canal"):
        assert private not in subject and private not in body
    with connect() as c:
        payload = rows(c, "SELECT payload FROM notifications WHERE tenant_id = ?", clinic["id"])[0]["payload"]
    assert "Dana" not in payload
