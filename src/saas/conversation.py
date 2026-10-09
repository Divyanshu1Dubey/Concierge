"""Conversation state machine and widget-facing chat engine."""

from __future__ import annotations

import logging
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from saas.repositories import append_message, complete_conversation, create_conversation

logger = logging.getLogger(__name__)


class State(StrEnum):
    STARTED = "started"
    IDENTIFYING_INTENT = "identifying_intent"
    COLLECTING_INFORMATION = "collecting_information"
    QUALIFYING = "qualifying"
    CONFIRMING = "confirming"
    SUBMITTING = "submitting"
    SUBMITTED = "submitted"
    HANDOFF = "handoff"
    CLOSED = "closed"


class FieldDef(BaseModel):
    key: str
    label: str
    type: str = "text"
    required: bool = False
    ask: bool = True
    intent_only: list[str] | None = None


class ConversationContext(BaseModel):
    conversation_id: int
    tenant_id: int
    state: State = State.STARTED
    fields: dict[str, Any] = Field(default_factory=dict)
    turn_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


DEFAULT_GREETING = "Hi! How can we help today?"
DEFAULT_SERVICE_OPTIONS = ["Checkup & cleaning", "Implants", "Restorative (fillings, crowns)", "Emergency",
                           "Something else"]
WELCOME_BY_INTENT = {
    "appointment_request": "Sure, I can help with that. What's your name?",
    "emergency": "I'm sorry you're in pain. Let's get you help fast. What's your name?",
    "question": "I can pass this to the front desk. What's your name?",
}


_INTAKE_KEYS = {"name", "email", "phone", "service", "intent", "preferred_date", "preferred_time", "insurance"}
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
_PHONE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
# "my name is X" anywhere; "I'm X" / "this is X" only at the start of the message (after an optional greeting),
# so sentences like "this is urgent" or "I'm thinking about implants" mid-message aren't read as names.
_NAME_INTRO = re.compile(r"(?:(?P<explicit>\bmy name is|\bname's)|^\s*(?:(?:hi|hello|hey)\b[\s,!.]*)?"
                         r"(?:i am|i'm|im|this is|it's))\s+"
                         r"(?P<name>[^\W\d_](?:[^\W\d_]|['\-])+(?:\s+[^\W\d_](?:[^\W\d_]|['\-])+)?)", re.I)
# Phone keyboards type curly apostrophes ("Sean O’Brien", "I’m"): read them as plain ones.
_QUOTES = str.maketrans({"\N{RIGHT SINGLE QUOTATION MARK}": "'", "\N{LEFT SINGLE QUOTATION MARK}": "'",
                         "\N{MODIFIER LETTER APOSTROPHE}": "'"})
# Words that follow "I'm" / "I am" but are not names ("I'm in pain", "I am looking for ...").
_NOT_NAMES = {"in", "having", "looking", "a", "an", "not", "so", "very", "interested", "calling", "wondering", "new",
              "here", "trying", "just", "the", "sorry", "good", "fine", "ok", "okay", "still", "available", "free",
              "hoping", "needing", "experiencing", "currently", "also", "really", "on", "at", "with", "from",
              "scared", "worried", "nervous", "due", "going", "getting", "feeling", "bleeding", "swollen",
              "my", "and", "for", "about", "but", "or", "missing", "thinking", "urgent", "emergency", "asking",
              "reaching", "writing", "contacting", "your", "their", "our", "this", "that", "it", "is", "was", "be",
              "need", "needs", "want", "wanting", "planning", "considering", "having", "booking", "requesting",
              "email", "phone", "number", "patient", "new", "existing", "back", "ready", "done", "all", "set",
              "hurting", "hurt", "hurts", "broken", "cracked", "chipped", "sore", "pain", "painful", "severe"}
# Words that are never part of a reply to "what's your name?" ("sure", "ok", "hi", "I want veneers").
_NON_NAME_WORDS = {"sure", "ok", "okay", "yes", "yeah", "yep", "yup", "no", "nope", "nah", "hi", "hello", "hey",
                   "thanks", "thank", "thx", "you", "please", "i", "i'm", "im", "me", "my", "want", "need", "what",
                   "why", "how", "who", "maybe", "idk", "skip", "help", "none", "nothing", "cool", "great",
                   "a", "the", "to", "for", "at", "is", "are", "am", "it", "this", "that", "of", "with", "and", "or",
                   "there", "lot", "bad", "much", "dental", "dentist", "appointment", "today", "tomorrow"}

# Pain, injury or infection makes the request urgent. Whole words, common inflections. The <ctx> words also show up
# in routine requests ("severe dental anxiety", "veneers for my chipped teeth"), so they need a tooth, jaw, etc.
# nearby. Same list as EMERGENCY_RE in static/widget.js: keep the two in step.
_EMERGENCY = re.compile(
    r"\b(?:emergenc(?:y|ies)|urgent(?:ly)?|tooth[- ]?aches?|ach(?:e|es|ing)|hurt(?:s|ing)?|pain(?:s|ful|killers?)?"
    r"|throb(?:s|bing|bed)?|killing me|bleed(?:s|ing)?|bled|abscess(?:es|ed)?|swell(?:s|ing|ed|en)?|swollen"
    r"|knock(?:ed)?[- ]out|knocked (?:[a-z']+ ){1,3}out|fever|f[ae]ll(?:en|s)? (?:out|off)"
    r"|lost (?:a|my|the) (?:[a-z]+ )?(?:tooth|teeth|filling|crown|cap)|infection|infected|can'?t sleep|cannot sleep"
    r"|(?P<ctx>sever(?:e|ely)|brok(?:e|en)|crack(?:ed|s)?|chip(?:ped|s)?))\b")
# "no pain", "not urgent", "without any pain", "doesn't hurt" (but "doesn't stop bleeding" is still urgent).
_NEGATIONS = {"no", "not", "non", "without", "never", "nothing", "none", "isn't", "isnt", "wasn't", "wasnt", "aren't",
              "arent", "don't", "dont", "doesn't", "doesnt", "didn't", "didnt", "hasn't", "hasnt", "haven't", "havent"}
_STOP_WORDS = {"stop", "stops", "stopped", "stopping"}
_INJURY_CONTEXT = {"tooth", "teeth", "molar", "molars", "crown", "crowns", "filling", "fillings", "jaw", "gum", "gums",
                   "mouth", "face", "lip", "cheek", "cap", "implant", "denture", "dentures", "wisdom", "root"}
_COSMETIC = re.compile(r"\b(?:veneers?|whiten(?:ing)?|bonding|cosmetic|smile makeover|invisalign|aligners?)\b")


def _negated(before: str, after: str) -> bool:
    """A negation a few words before the keyword in the same clause, or "-free" / "-less" right after it."""
    if re.match(r"(?:-|\s)?(?:free|less)\b", after):
        return True
    words = re.findall(r"[a-z']+", re.split(r"[.;!?,]|\bbut\b", before)[-1])[-3:]
    hits = [i for i, w in enumerate(words) if w in _NEGATIONS]
    return bool(hits) and not any(w in _STOP_WORDS for w in words[hits[-1] + 1:])


def _is_emergency(text: str) -> bool:
    """Lower-cased text with emails removed: does the patient report pain, injury or infection?"""
    cosmetic = _COSMETIC.search(text)
    for m in _EMERGENCY.finditer(text):
        if _negated(text[:m.start()], text[m.end():]):
            continue
        if m.group("ctx"):
            nearby = re.findall(r"[a-z']+", text[:m.start()])[-4:] + re.findall(r"[a-z']+", text[m.end():])[:4]
            if cosmetic or not _INJURY_CONTEXT.intersection(nearby):
                continue
        return True
    return False


_SERVICES = ["cleaning", "checkup", "check-up", "exam", "whitening", "crown", "filling", "implant", "root canal",
             "extraction", "veneers", "invisalign", "consult"]


def _not_a_name_word(word: str) -> bool:
    return (word in _NON_NAME_WORDS or word in _NOT_NAMES or word in _INJURY_CONTEXT or word in _SERVICES
            or word.rstrip("s") in _SERVICES or bool(_EMERGENCY.fullmatch(word)))


def _plausible_name(text: str, max_words: int = 6, retry: bool = False) -> bool:
    """A few words of letters, and not only chat filler, services or symptoms ("Sure", "Hi there", "I want veneers").

    Real names that happen to be words still pass: "My Tran", "Kim Ok", "Linh To", "Hope Severe". On a retry (the
    name was already asked again) any short answer without digits or "@" is taken, so nobody is asked forever."""
    text = text.translate(_QUOTES)
    words = [w.lower().strip(".") for w in text.split()]
    if not 0 < len(words) <= max_words or re.search(r"[\d@]", text) or not re.search(r"[^\W\d_]", text):
        return False
    if retry:
        return not _is_emergency(" ".join(words))  # "it hurts so much" is still not a name
    if not all(re.fullmatch(r"[^\W\d_](?:[^\W\d_]|['.\-])*", w) for w in words):
        return False  # commas, symbols: a sentence, not a name
    if all(_not_a_name_word(w) for w in words):
        return False
    # "Sam my tooth hurts" is a sentence about symptoms; a two-word name like "Ann Pain" still passes.
    return len(words) <= 2 or not _is_emergency(" ".join(words))


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] for w in text.split())


def _rule_fields(body: str, asked: str | None, name_retry: bool = False) -> dict[str, Any]:
    """Rules-only reading of one message. name_retry: the name was already asked twice, so take the bare answer."""
    text = body.strip().translate(_QUOTES)
    lowered = text.lower()
    out: dict[str, Any] = {}
    m = _EMAIL.search(text)
    if m:
        out["email"] = m.group(0)
    m = _PHONE.search(text)
    if m:
        out["phone"] = m.group(0).strip()
    # Keywords never match inside an email address ("avi@example.test" is not an "exam", "pain@x.test" no emergency).
    words_only = _EMAIL.sub(" ", lowered)
    m = _NAME_INTRO.search(text)
    if m:
        words = []
        for i, w in enumerate(m.group("name").split()):
            # "I'm in pain" is not a name; after "my name is" the first word always is ("My name is My Tran").
            if w.lower() in _NOT_NAMES and not (i == 0 and m.group("explicit")):
                break
            words.append(w)
        if words and _plausible_name(" ".join(words)):
            out["name"] = _title(" ".join(words))
    # A bare answer to "what's your name?" ("An Nguyen", or "I'm An Nguyen" without the "I'm"), once any email or
    # phone in the same message is set aside.
    bare = _PHONE.sub(" ", _EMAIL.sub(" ", text[m.start("name"):] if m else text)).strip(" ,.;:!")
    if "name" not in out and asked == "name" and _plausible_name(bare, max_words=6 if name_retry else 5,
                                                                 retry=name_retry):
        out["name"] = _title(bare)
    if _is_emergency(words_only):
        out["intent"] = "emergency"
    elif any(k in words_only for k in ["new patient", "first time", "never been"]):
        out["intent"] = "new_patient"
    elif any(k in words_only for k in ["cleaning", "checkup", "check-up", "exam", "appointment", "whitening", "crown",
                                       "filling", "implant", "consult"]):
        out["intent"] = "appointment_request"
    service = next((k for k in _SERVICES if re.search(r"\b" + re.escape(k) + r"\b", words_only)), None)
    if service:
        out["service"] = service
    if asked == "service" and "intent" not in out and not out.get("email"):
        out["service"] = text[:120]
    return out


class ConversationEngine:
    def __init__(self, tenant_config: dict[str, Any]) -> None:
        self.config = tenant_config

    def start(self, tenant_id: int, page_url: str | None, referrer: str | None, user_agent: str | None,
              visitor_id: str | None) -> dict:
        conv = create_conversation(tenant_id, page_url, referrer, user_agent, visitor_id)
        append_message(conv["id"], "assistant", self.config.get("greeting", DEFAULT_GREETING))
        return {"conversation_id": conv["id"], "state": State.STARTED.value,
                "reply": self.config.get("greeting", DEFAULT_GREETING), "options": self.options_for(None)}

    def handle(self, context: ConversationContext, body: str) -> dict:
        context.turn_count += 1
        context.state = State.COLLECTING_INFORMATION
        append_message(context.conversation_id, "user", body)
        reply = self._reply_for(context, body)
        append_message(context.conversation_id, "assistant", reply)
        if context.state in (State.SUBMITTED, State.HANDOFF):
            complete_conversation(context.conversation_id, context.fields.get("_summary"))
        out = {"conversation_id": context.conversation_id, "state": context.state.value, "reply": reply,
                "fields": context.fields, "turn_count": context.turn_count}
        options = self.options_for(context.fields.get("_asked")) if context.state not in (State.SUBMITTED, State.HANDOFF) else []
        if options:
            out["options"] = options
        if context.state == State.SUBMITTED and self._wants_callback_number(context.fields):
            out["followup"] = "phone"  # the widget keeps the message box open for the optional callback number
        return out

    def after_submit(self, context: ConversationContext, body: str) -> dict:
        """The request was already sent: keep the extra message with it, but it is not a new request.

        A phone number (the optional callback number after an urgent request) is added to context.fields; the
        caller saves it onto the lead that already exists."""
        append_message(context.conversation_id, "user", body)
        phone = None if context.fields.get("phone") else _PHONE.search(body)
        if phone:
            context.fields["phone"] = phone.group(0).strip()
            reply = "Thanks, I've added your phone number to your request."
            if context.fields.get("intent") == "emergency":
                reply += " Our team will call you back as soon as they can."
        else:
            reply = "Thanks, our team already has your request and will email you soon."
        if context.fields.get("intent") == "emergency":
            reply += f" If it's urgent, {self._call_now()}."
        append_message(context.conversation_id, "assistant", reply)
        return {"conversation_id": context.conversation_id, "state": State.SUBMITTED.value, "reply": reply,
                "fields": context.fields, "turn_count": context.turn_count}

    def _clinic_phone(self) -> str:
        return ((self.config.get("clinic") or {}).get("phone") or "").strip()

    def _call_now(self) -> str:
        phone = self._clinic_phone()
        return f"please call us now at {phone}" if phone else "please call our office now"

    @staticmethod
    def _wants_callback_number(fields: dict[str, Any]) -> bool:
        return fields.get("intent") == "emergency" and not fields.get("phone")

    def _reply_for(self, context: ConversationContext, body: str) -> str:
        was_emergency = context.fields.get("intent") == "emergency"
        asked = context.fields.get("_asked")
        fields = self._extract_fields(body, context.fields)
        context.fields.update(fields)
        missing = self._missing_required(context.fields)
        if not missing:
            context.state = State.SUBMITTED
            if context.fields.get("intent") == "emergency":
                # Sent now, so an abandoned chat still reaches the front desk; the callback number is optional.
                reply = (f"Thanks, I've sent this to our front desk as urgent. Since you're in pain, "
                         f"{self._call_now()} so we can see you as soon as possible. If you have trouble breathing or "
                         "swallowing, call 911.")
                if self._wants_callback_number(context.fields):
                    reply += " If you'd like us to call you back, reply with your phone number."
                return reply
            return "Thanks, I have everything I need. Our front desk will follow up shortly."
        if context.turn_count >= self.config.get("max_turns", 8):
            context.state = State.HANDOFF
            phone = self._clinic_phone()
            return "Let me connect you with our front desk." + (f" You can call us at {phone}." if phone else "")
        next_field = missing[0]
        context.fields["_asked"] = next_field
        context.fields["_reasked"] = next_field == asked  # asked twice: take the next answer as it is (names)
        if context.fields.get("intent") == "emergency" and not was_emergency:
            # Say "call us" first, before collecting anything: the website can't book an urgent visit.
            return (f"I'm sorry you're dealing with this. If it's urgent, {self._call_now()}. If you have trouble "
                    f"breathing or swallowing, call 911. I'll also flag this as urgent for our team. "
                    f"{self._ask_for(next_field)}")
        if next_field == asked:
            return self._ask_again(next_field)
        return self._ask_for(next_field)

    def options_for(self, field: str | None) -> list[str]:
        """Tap-to-answer choices shown under a question. Clinics can override via the 'service_options' setting."""
        # None = the opening greeting: offer the same choices so one tap answers "how can we help?"
        if field not in (None, "service"):
            return []
        custom = self.config.get("service_options")
        if isinstance(custom, list) and custom:
            return [str(o)[:60] for o in custom][:8]
        return list(DEFAULT_SERVICE_OPTIONS)

    def _ask_for(self, field: str) -> str:
        prompts = {
            "name": "Can I get your name?",
            "email": "What email should we use?",
            "phone": "What's the best phone number to reach you?",
            "service": "What are you looking to schedule?",
            "preferred_date": "What day works best?",
            "preferred_time": "What time of day do you prefer?",
            "message": "Anything else we should know?",
        }
        return prompts.get(field, f"Could you share your {field}?")

    def _ask_again(self, field: str) -> str:
        """Same question twice in a row: the last answer didn't fit, so say so politely."""
        if field == "name":
            return "Sorry, I didn't catch your name. What name should we put this request under?"
        if field == "email":
            return "Sorry, I didn't catch an email address. What email should we use?"
        return self._ask_for(field)

    def _extract_fields(self, body: str, existing: dict[str, Any]) -> dict[str, Any]:
        """Gemini reads the message first; the rules below fill anything it missed (or all of it when AI is off).

        The keyword emergency rule only applies when Gemini gave no intent: Gemini understands "no pain at all" or
        "veneers for my chipped teeth" as routine, and the rules skip those too (negations, cosmetic requests)."""
        asked = existing.get("_asked")
        out: dict[str, Any] = {}
        if self.config.get("ai_enabled", True):
            try:
                from saas.ai_engine import extract_intake
                out = {k: v for k, v in extract_intake(body, existing, asked).items() if k in _INTAKE_KEYS}
            except Exception:
                logger.exception("AI intake extraction failed; using rules")
        if out.get("name"):
            out["name"] = str(out["name"]).translate(_QUOTES).strip()
            if not _plausible_name(out["name"]):
                out.pop("name")  # "Sure", "Hi there", "I Want Veneers" are not names: use the rules' reading
        rules = _rule_fields(body, asked, name_retry=asked == "name" and bool(existing.get("_reasked")))
        for key, value in rules.items():
            out.setdefault(key, value)
        explicit_name = re.search(r"\bmy name is\b|\bname's\b", body, re.I)
        if existing.get("name") and "name" in out and asked != "name" and not explicit_name:
            out.pop("name")  # never overwrite a name the patient already gave
        if existing.get("service") and "service" in out and asked != "service":
            out.pop("service")  # keep what the patient already chose
        # A tapped choice is the patient's exact answer: store the label they picked.
        picked = next((o for o in self.options_for(asked) if o.lower() == body.strip().lower()), None)
        if picked:
            out["service"] = picked
        if out.get("email") and not _EMAIL.fullmatch(out["email"]):
            out.pop("email")
        if existing.get("intent") == "emergency":
            out.pop("intent", None)  # once urgent, always urgent: "also a cleaning" must not downgrade it
        return out

    def _missing_required(self, fields: dict[str, Any]) -> list[str]:
        configured = [f["key"] if isinstance(f, dict) else f.key for f in (self.config.get("fields") or [])
                      if (f.get("required") if isinstance(f, dict) else f.required)]
        if configured:
            required = configured
        else:
            # Ask what they need first (shown with tap-to-answer choices), then contact details. An emergency is sent
            # as soon as these are known; the callback number is asked for after, so an abandoned chat isn't lost.
            required = ([] if fields.get("intent") or fields.get("service") else ["service"]) + ["name", "email"]
        missing = [f for f in required if not fields.get(f)]
        return missing
