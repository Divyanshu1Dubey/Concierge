"""Branded HTML for ordinary staff replies to patients (the plain-text part is sent alongside)."""
from django.template.loader import render_to_string


def render_branded_message(practice, body_text: str) -> str:
    from apps.appointments.offers import branding
    return render_to_string('emails/branded_message.html', {'brand': branding(practice), 'message': (body_text or '').strip()})