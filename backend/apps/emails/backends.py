"""
HTTPS email backend (Resend API). Used when RESEND_API_KEY is set, so mail works on hosts that block
outbound SMTP ports (for example Railway's Hobby plan). Keeps HTML + text parts, Reply-To and
threading headers (Message-ID / In-Reply-To / References).
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)
RESEND_URL = 'https://api.resend.com/emails'


class EmailAPIError(Exception):
    def __init__(self, status, message=''):
        super().__init__(message or f'Email API error {status}')
        self.status = status


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        self.timeout = getattr(settings, 'EMAIL_TIMEOUT', 15) or 15

    def _payload(self, msg):
        html = None
        for content, mimetype in getattr(msg, 'alternatives', []) or []:
            if mimetype == 'text/html':
                html = content
        payload = {
            'from': msg.from_email,
            'to': list(msg.to),
            'subject': msg.subject,
            'text': msg.body,
        }
        if msg.cc:
            payload['cc'] = list(msg.cc)
        if msg.bcc:
            payload['bcc'] = list(msg.bcc)
        if msg.reply_to:
            payload['reply_to'] = list(msg.reply_to)
        if html:
            payload['html'] = html
        headers = {k: str(v) for k, v in (msg.extra_headers or {}).items()}
        if headers:
            payload['headers'] = headers
        return payload

    def _post(self, payload):
        req = urllib.request.Request(
            RESEND_URL, data=json.dumps(payload).encode('utf-8'), method='POST',
            headers={'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json',
                     'User-Agent': 'HeyJarvis-Concierge'},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as res:
                return json.loads(res.read() or b'{}')
        except urllib.error.HTTPError as exc:
            raise EmailAPIError(exc.code) from None

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for msg in email_messages:
            if not msg.recipients():
                continue
            try:
                self._post(self._payload(msg))
                sent += 1
            except Exception as exc:
                logger.warning('Email API send failed: %s', type(exc).__name__)
                if not self.fail_silently:
                    raise
        return sent