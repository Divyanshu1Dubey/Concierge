"""Email template engine for HeyJarvis Concierge."""

from __future__ import annotations

from typing import Any


# Default templates keyed by intent/type.
# Variables use {{variable_name}} syntax.
DEFAULT_TEMPLATES: dict[str, dict[str, str]] = {
    "default": {
        "subject": "New lead from {{tenant_name}}",
        "body": """Hi,

You have a new lead from your HeyJarvis Concierge widget.

Name: {{name}}
Email: {{email}}
Phone: {{phone}}
Intent: {{intent}}
Service: {{service}}
Preferred Date: {{preferred_date}}
Preferred Time: {{preferred_time}}
Message: {{message}}

Conversation Summary:
{{conversation_summary}}

---
This lead came from: {{page_url}}
Conversation ID: {{conversation_id}}""",
    },
    "new_patient": {
        "subject": "New Patient Request — {{tenant_name}}",
        "body": """Hi Front Desk,

A new patient request has come through the Concierge widget.

Patient: {{name}}
Email: {{email}}
Phone: {{phone}}
Service Requested: {{service}}
Preferred Date: {{preferred_date}}
Preferred Time: {{preferred_time}}
Insurance: {{insurance}}
Financing: {{financing}}

Message:
{{message}}

Conversation Summary:
{{conversation_summary}}

---
Source: {{page_url}}
Conversation ID: {{conversation_id}}""",
    },
    "emergency": {
        "subject": "URGENT: Emergency Appointment Request — {{tenant_name}}",
        "body": """URGENT — Front Desk Attention Needed

An emergency appointment request has been submitted via the Concierge widget.

Patient: {{name}}
Email: {{email}}
Phone: {{phone}}
Service: {{service}}
Preferred Date: {{preferred_date}}
Preferred Time: {{preferred_time}}

Message:
{{message}}

Conversation Summary:
{{conversation_summary}}

Please contact this patient as soon as possible.

---
Source: {{page_url}}
Conversation ID: {{conversation_id}}""",
    },
    "existing_patient": {
        "subject": "Appointment Request — {{tenant_name}}",
        "body": """Hi Front Desk,

An existing patient has submitted an appointment request.

Patient: {{name}}
Email: {{email}}
Phone: {{phone}}
Service: {{service}}
Preferred Date: {{preferred_date}}
Preferred Time: {{preferred_time}}

Message:
{{message}}

Conversation Summary:
{{conversation_summary}}

---
Source: {{page_url}}
Conversation ID: {{conversation_id}}""",
    },
    "question": {
        "subject": "Question from Website Visitor — {{tenant_name}}",
        "body": """Hi Front Desk,

A website visitor has a question submitted via the Concierge widget.

Name: {{name}}
Email: {{email}}
Phone: {{phone}}

Question/Message:
{{message}}

Conversation Summary:
{{conversation_summary}}

---
Source: {{page_url}}
Conversation ID: {{conversation_id}}""",
    },
    "test": {
        "subject": "Test Email — {{tenant_name}} Concierge",
        "body": """This is a test email from your HeyJarvis Concierge.

If you received this, your email settings are configured correctly.

---
Tenant: {{tenant_name}}
Time: {{timestamp}}""",
    },
}

# Available template variables with descriptions
TEMPLATE_VARIABLES: dict[str, str] = {
    "{{patient_name}}": "Patient's full name",
    "{{name}}": "Patient's full name (alias)",
    "{{email}}": "Patient's email address",
    "{{phone}}": "Patient's phone number",
    "{{intent}}": "Request intent (new_patient, emergency, etc.)",
    "{{service}}": "Requested service or reason",
    "{{preferred_date}}": "Preferred appointment date",
    "{{preferred_time}}": "Preferred appointment time",
    "{{insurance}}": "Insurance information",
    "{{financing}}": "Financing information",
    "{{message}}": "Patient's message",
    "{{conversation_summary}}": "Summary of the conversation",
    "{{page_url}}": "URL where the conversation started",
    "{{conversation_id}}": "Conversation ID",
    "{{tenant_name}}": "Business/tenant name",
    "{{timestamp}}": "Current timestamp",
}


def render_template(template_body: str, payload: dict[str, Any]) -> str:
    """Render a template string by replacing {{variables}} with payload values."""
    out = template_body
    for key, value in (payload or {}).items():
        placeholder = "{{" + key + "}}"
        out = out.replace(placeholder, str(value or ""))
    return out


def get_default_template(intent: str = "default") -> dict[str, str]:
    """Get the default template for a given intent."""
    return DEFAULT_TEMPLATES.get(intent, DEFAULT_TEMPLATES["default"])


def list_template_variables() -> dict[str, str]:
    """Return available template variables and their descriptions."""
    return dict(TEMPLATE_VARIABLES)


def build_payload(tenant_name: str, lead: dict[str, Any] | None = None,
                  conversation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a template payload from tenant, lead, and conversation data."""
    import time
    payload: dict[str, Any] = {
        "tenant_name": tenant_name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if lead:
        for key in [
            "name", "email", "phone", "intent", "service", "urgency",
            "preferred_date", "preferred_time", "insurance", "financing",
            "message", "conversation_summary", "page_url",
        ]:
            payload[key] = lead.get(key, "")
        payload["conversation_id"] = lead.get("conversation_id", "")
    if conversation:
        payload.setdefault("conversation_summary", conversation.get("summary", ""))
        payload.setdefault("page_url", conversation.get("page_url", ""))
    return payload
