"""
Outside-service adapters: Google Business Profile (OAuth, locations, reviews, review replies, posts)
and NexHealth Synchronizer (practice-management availability). Credentials are stored encrypted on the
practice's Integration row and never returned by the API.

Readiness (be honest in the UI):
- Google Business Profile needs GOOGLE_BUSINESS_CLIENT_ID / GOOGLE_BUSINESS_CLIENT_SECRET from a Google
  Cloud project that Google has approved for Business Profile API access, then each practice connects
  its own profile. Without that approval the API returns errors even with valid OAuth.
- NexHealth needs an API key (sandbox or production), the practice's subdomain and location id, and a
  signed BAA before real patient data is synced.

Endpoints (verified against official reference pages, Oct 2026):
- GBP review reply: PUT https://mybusiness.googleapis.com/v4/{accounts/*/locations/*/reviews/*}/reply
- NexHealth auth:   POST https://nexhealth.info/authenticates  (Authorization: <api key>, Nex-Api-Version)
                    token at data.token, valid 1h in production; then Authorization: Bearer <token>
- NexHealth booking: POST https://nexhealth.info/appointments?subdomain=..&location_id=..
"""
import json
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core import signing
from django.utils import timezone

from apps.core.security import decrypt_secret, encrypt_secret

from .models import Integration

logger = logging.getLogger(__name__)
TIMEOUT = 15


class IntegrationError(Exception):
    pass


def get_integration(practice, kind) -> Integration:
    obj, _ = Integration.objects.get_or_create(practice=practice, kind=kind)
    return obj


def read_secret(integ) -> dict:
    if not integ.secret:
        return {}
    try:
        return json.loads(decrypt_secret(integ.secret) or '{}')
    except ValueError:
        return {}


def write_secret(integ, data: dict):
    integ.secret = encrypt_secret(json.dumps(data)) if data else ''


def mark(integ, status, error=''):
    integ.status = status
    integ.last_error = (error or '')[:300]
    integ.last_checked_at = timezone.now()
    integ.save()


# ── Google Business Profile ───────────────────────────────────────────────────────────────────

GOOGLE_AUTH = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN = 'https://oauth2.googleapis.com/token'
GOOGLE_REVOKE = 'https://oauth2.googleapis.com/revoke'
GBP_SCOPE = 'https://www.googleapis.com/auth/business.manage'
ACCOUNTS_API = 'https://mybusinessaccountmanagement.googleapis.com/v1/accounts'
INFO_API = 'https://mybusinessbusinessinformation.googleapis.com/v1'
V4_API = 'https://mybusiness.googleapis.com/v4'
OAUTH_STATE_SALT = 'growth.gbp.oauth'


def gbp_app_configured() -> bool:
    return bool(getattr(settings, 'GOOGLE_BUSINESS_CLIENT_ID', '') and getattr(settings, 'GOOGLE_BUSINESS_CLIENT_SECRET', ''))


def gbp_redirect_uri() -> str:
    base = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
    return f"{base}/api/v1/growth/integrations/google/callback/"


def gbp_authorize_url(practice, user) -> str:
    if not gbp_app_configured():
        raise IntegrationError('Google Business Profile is not set up on this HeyJarvis server yet '
                               '(GOOGLE_BUSINESS_CLIENT_ID / GOOGLE_BUSINESS_CLIENT_SECRET).')
    state = signing.dumps({'p': str(practice.id), 'u': str(user.id), 'n': secrets.token_urlsafe(8)}, salt=OAUTH_STATE_SALT)
    integ = get_integration(practice, 'google_business')
    integ.status = 'pending'
    integ.save(update_fields=['status', 'updated_at'])
    return GOOGLE_AUTH + '?' + urlencode({
        'client_id': settings.GOOGLE_BUSINESS_CLIENT_ID, 'redirect_uri': gbp_redirect_uri(),
        'response_type': 'code', 'scope': GBP_SCOPE, 'access_type': 'offline', 'prompt': 'consent',
        'include_granted_scopes': 'true', 'state': state,
    })


def gbp_read_state(state: str):
    try:
        return signing.loads(state, salt=OAUTH_STATE_SALT, max_age=900)
    except signing.BadSignature:
        return None


def gbp_exchange_code(practice, user, code: str) -> Integration:
    integ = get_integration(practice, 'google_business')
    try:
        resp = requests.post(GOOGLE_TOKEN, data={
            'code': code, 'client_id': settings.GOOGLE_BUSINESS_CLIENT_ID,
            'client_secret': settings.GOOGLE_BUSINESS_CLIENT_SECRET, 'redirect_uri': gbp_redirect_uri(),
            'grant_type': 'authorization_code'}, timeout=TIMEOUT)
    except requests.RequestException:
        mark(integ, 'error', 'Could not reach Google. Try connecting again.')
        raise IntegrationError(integ.last_error)
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or 'access_token' not in data:
        mark(integ, 'error', 'Google did not accept the connection. Try again.')
        raise IntegrationError(integ.last_error)
    write_secret(integ, {'refresh_token': data.get('refresh_token', ''), 'access_token': data['access_token'],
                         'expires_at': (timezone.now() + timedelta(seconds=int(data.get('expires_in', 3600)) - 60)).isoformat()})
    integ.connected_by = user
    mark(integ, 'connected')
    return integ


def _gbp_token(integ) -> str:
    secret = read_secret(integ)
    expires = secret.get('expires_at', '')
    if secret.get('access_token') and expires and timezone.datetime.fromisoformat(expires) > timezone.now():
        return secret['access_token']
    if not secret.get('refresh_token'):
        mark(integ, 'error', 'The Google connection expired. Connect again.')
        raise IntegrationError(integ.last_error)
    try:
        resp = requests.post(GOOGLE_TOKEN, data={
            'refresh_token': secret['refresh_token'], 'client_id': settings.GOOGLE_BUSINESS_CLIENT_ID,
            'client_secret': settings.GOOGLE_BUSINESS_CLIENT_SECRET, 'grant_type': 'refresh_token'}, timeout=TIMEOUT)
    except requests.RequestException:
        raise IntegrationError('Could not reach Google. Try again shortly.')
    data = resp.json() if resp.content else {}
    if resp.status_code != 200 or 'access_token' not in data:
        mark(integ, 'error', 'Google access was revoked or expired. Connect again.')
        raise IntegrationError(integ.last_error)
    secret.update(access_token=data['access_token'],
                  expires_at=(timezone.now() + timedelta(seconds=int(data.get('expires_in', 3600)) - 60)).isoformat())
    write_secret(integ, secret)
    integ.save(update_fields=['secret', 'updated_at'])
    return data['access_token']


def _gbp_call(integ, method, url, **kwargs):
    token = _gbp_token(integ)
    try:
        resp = requests.request(method, url, headers={'Authorization': f'Bearer {token}'}, timeout=TIMEOUT, **kwargs)
    except requests.RequestException:
        raise IntegrationError('Could not reach Google. Try again shortly.')
    if resp.status_code == 403:
        mark(integ, 'error', 'Google refused access. The Business Profile API may not be approved for this '
                             'HeyJarvis project yet, or this account does not manage the profile.')
        raise IntegrationError(integ.last_error)
    if resp.status_code == 429:
        raise IntegrationError('Google rate limit reached. Try again in a minute.')
    if resp.status_code >= 400:
        raise IntegrationError(f'Google returned an error ({resp.status_code}).')
    return resp.json() if resp.content else {}


def gbp_locations(practice) -> list:
    integ = get_integration(practice, 'google_business')
    accounts = _gbp_call(integ, 'GET', ACCOUNTS_API).get('accounts', [])
    out = []
    for acct in accounts[:10]:
        data = _gbp_call(integ, 'GET', f"{INFO_API}/{acct['name']}/locations",
                         params={'readMask': 'name,title,phoneNumbers,storefrontAddress,websiteUri,regularHours',
                                 'pageSize': 100})
        for loc in data.get('locations', []):
            out.append({'account': acct['name'], 'name': loc.get('name'), 'title': loc.get('title', ''),
                        'phone': (loc.get('phoneNumbers') or {}).get('primaryPhone', ''),
                        'website': loc.get('websiteUri', ''),
                        'address': ', '.join((loc.get('storefrontAddress') or {}).get('addressLines', [])),
                        'postal_code': (loc.get('storefrontAddress') or {}).get('postalCode', ''),
                        'regular_hours': loc.get('regularHours') or {}})
    mark(integ, 'connected')
    return out


def gbp_select_location(practice, account: str, location: str, title: str = ''):
    integ = get_integration(practice, 'google_business')
    if not (account.startswith('accounts/') and location.startswith('locations/')):
        raise IntegrationError('Choose a location from the list.')
    integ.config = {**(integ.config or {}), 'account': account, 'location': location, 'title': title[:200]}
    integ.save(update_fields=['config', 'updated_at'])
    return integ


def _location_path(integ) -> str:
    cfg = integ.config or {}
    if not cfg.get('account') or not cfg.get('location'):
        raise IntegrationError('Choose which Google Business Profile location belongs to this practice.')
    return f"{cfg['account']}/{cfg['location']}"


STAR = {'ONE': 1, 'TWO': 2, 'THREE': 3, 'FOUR': 4, 'FIVE': 5}


def gbp_reviews(practice, page_token: str = '') -> dict:
    integ = get_integration(practice, 'google_business')
    params = {'pageSize': 50}
    if page_token:
        params['pageToken'] = page_token
    data = _gbp_call(integ, 'GET', f"{V4_API}/{_location_path(integ)}/reviews", params=params)
    reviews = [{
        'name': r.get('name'), 'reviewer': (r.get('reviewer') or {}).get('displayName', 'A Google user'),
        'rating': STAR.get(r.get('starRating'), None), 'comment': r.get('comment', ''),
        'created': r.get('createTime'), 'reply': (r.get('reviewReply') or {}).get('comment', ''),
    } for r in data.get('reviews', [])]
    return {'reviews': reviews, 'average_rating': data.get('averageRating'), 'total': data.get('totalReviewCount'),
            'next_page_token': data.get('nextPageToken', '')}


def gbp_reply(practice, review_name: str, comment: str):
    integ = get_integration(practice, 'google_business')
    loc = _location_path(integ)
    if not review_name.startswith(loc + '/reviews/'):
        raise IntegrationError('That review does not belong to this practice\'s location.')
    comment = (comment or '').strip()
    if not comment or len(comment) > 4000:
        raise IntegrationError('Write a reply (up to 4,000 characters).')
    return _gbp_call(integ, 'PUT', f"{V4_API}/{review_name}/reply", json={'comment': comment})


def gbp_post(practice, summary: str, cta_url: str = ''):
    integ = get_integration(practice, 'google_business')
    summary = (summary or '').strip()
    if not summary or len(summary) > 1500:
        raise IntegrationError('Write the update (up to 1,500 characters).')
    body = {'languageCode': 'en-US', 'summary': summary, 'topicType': 'STANDARD'}
    if cta_url:
        body['callToAction'] = {'actionType': 'BOOK', 'url': cta_url}
    return _gbp_call(integ, 'POST', f"{V4_API}/{_location_path(integ)}/localPosts", json=body)


def gbp_disconnect(practice):
    integ = get_integration(practice, 'google_business')
    secret = read_secret(integ)
    token = secret.get('refresh_token') or secret.get('access_token')
    if token:
        try:
            requests.post(GOOGLE_REVOKE, params={'token': token}, timeout=TIMEOUT)
        except requests.RequestException:
            pass
    integ.secret, integ.config = '', {}
    mark(integ, 'not_connected')


def draft_review_reply(practice, review: dict) -> str:
    """A short, polite reply that never confirms someone is a patient (privacy) or discusses treatment."""
    rating = review.get('rating') or 0
    name = (review.get('reviewer') or '').split(' ')[0]
    greeting = f"Hi {name}," if name and name.lower() not in ('a', 'google') else 'Hello,'
    if rating >= 4:
        text = (f"{greeting} thank you for taking the time to share this. "
                f"We're glad to hear it and appreciate your kind words. - The {practice.name} team")
    else:
        contact = f" at {practice.phone}" if practice.phone else ''
        text = (f"{greeting} thank you for your feedback. We take every comment seriously and would like to "
                f"understand more. Please contact our office{contact} so we can talk directly. - The {practice.name} team")
    try:
        from apps.ai_service.engine import AIEngine
        engine = AIEngine()
        if engine.available:
            res = engine.chat(
                "Rewrite this reply to a public Google review so it sounds warm and natural. Rules: under 70 words, "
                "do not confirm the reviewer is or was a patient, do not mention any treatment, health detail or "
                "appointment, no promises or discounts. Review: " + (review.get('comment') or '(no text)')[:800] +
                "\nDraft reply: " + text, practice=practice, audience='staff')
            if res.get('content'):
                return res['content'].strip()[:1200]
    except Exception:
        pass
    return text


# ── NexHealth Synchronizer ────────────────────────────────────────────────────────────────────

NEX_BASE = 'https://nexhealth.info'
NEX_VERSION = 'v3.0.0'


def nex_save(practice, user, api_key: str, subdomain: str, location_id: str):
    integ = get_integration(practice, 'nexhealth')
    subdomain = (subdomain or '').strip()[:80]
    location_id = str(location_id or '').strip()
    if not subdomain or not location_id.isdigit():
        raise IntegrationError('Enter the NexHealth subdomain and numeric location ID.')
    secret = read_secret(integ)
    if api_key:
        secret['api_key'] = api_key.strip()
        secret.pop('token', None)
    if not secret.get('api_key'):
        raise IntegrationError('Enter the NexHealth API key.')
    write_secret(integ, secret)
    integ.config = {**(integ.config or {}), 'subdomain': subdomain, 'location_id': int(location_id)}
    integ.connected_by = user
    integ.status = 'pending'
    integ.save()
    return integ


def _nex_token(integ) -> str:
    secret = read_secret(integ)
    if secret.get('token') and secret.get('token_expires', '') > timezone.now().isoformat():
        return secret['token']
    if not secret.get('api_key'):
        raise IntegrationError('NexHealth is not connected.')
    try:
        resp = requests.post(f'{NEX_BASE}/authenticates',
                             headers={'Authorization': secret['api_key'], 'Nex-Api-Version': NEX_VERSION},
                             timeout=TIMEOUT)
    except requests.RequestException:
        raise IntegrationError('Could not reach NexHealth. Try again shortly.')
    data = resp.json() if resp.content else {}
    token = (data.get('data') or {}).get('token') if isinstance(data, dict) else None
    if resp.status_code >= 400 or not token:
        mark(integ, 'error', 'NexHealth rejected the API key.')
        raise IntegrationError(integ.last_error)
    secret.update(token=token, token_expires=(timezone.now() + timedelta(minutes=50)).isoformat())
    write_secret(integ, secret)
    integ.save(update_fields=['secret', 'updated_at'])
    return token


def _nex_get(integ, path, params):
    token = _nex_token(integ)
    cfg = integ.config or {}
    query = {'subdomain': cfg.get('subdomain', ''), **params}
    try:
        resp = requests.get(f'{NEX_BASE}{path}', params=query,
                            headers={'Authorization': f'Bearer {token}', 'Nex-Api-Version': NEX_VERSION}, timeout=TIMEOUT)
    except requests.RequestException:
        raise IntegrationError('Could not reach NexHealth. Try again shortly.')
    if resp.status_code >= 400:
        raise IntegrationError(f'NexHealth returned an error ({resp.status_code}).')
    return resp.json() if resp.content else {}


def nex_test(practice) -> dict:
    integ = get_integration(practice, 'nexhealth')
    cfg = integ.config or {}
    data = _nex_get(integ, '/providers', {'location_id': cfg.get('location_id'), 'per_page': 50})
    providers = data.get('data') or []
    if isinstance(providers, dict):
        providers = providers.get('providers', [])
    mark(integ, 'connected')
    return {'providers': [{'id': p.get('id'), 'name': p.get('name') or
                           ' '.join(t for t in (p.get('first_name'), p.get('last_name')) if t)} for p in providers][:50]}


def nex_slots(practice, start_date: str, days: int = 7, provider_ids=None) -> dict:
    integ = get_integration(practice, 'nexhealth')
    cfg = integ.config or {}
    params = [('start_date', start_date), ('days', max(1, min(int(days), 14))), ('lids[]', cfg.get('location_id'))]
    for pid in (provider_ids or cfg.get('provider_ids') or [])[:10]:
        params.append(('pids[]', pid))
    token = _nex_token(integ)
    try:
        resp = requests.get(f'{NEX_BASE}/appointment_slots', params=[('subdomain', cfg.get('subdomain', ''))] + params,
                            headers={'Authorization': f'Bearer {token}', 'Nex-Api-Version': NEX_VERSION}, timeout=TIMEOUT)
    except requests.RequestException:
        raise IntegrationError('Could not reach NexHealth. Try again shortly.')
    if resp.status_code >= 400:
        raise IntegrationError(f'NexHealth returned an error ({resp.status_code}).')
    data = resp.json().get('data') or []
    slots = []
    for block in data if isinstance(data, list) else []:
        for s in block.get('slots', [])[:200]:
            slots.append({'time': s.get('time'), 'end_time': s.get('end_time'),
                          'provider_id': block.get('pid'), 'operatory_id': s.get('operatory_id')})
    return {'slots': slots[:300], 'next_available_date': (data[0].get('next_available_date') if data and isinstance(data, list) else None)}


def nex_disconnect(practice):
    integ = get_integration(practice, 'nexhealth')
    integ.secret, integ.config = '', {}
    mark(integ, 'not_connected')


# ── Twilio (per-practice account) ─────────────────────────────────────────────────────────────

def twilio_save(practice, user, account_sid: str, auth_token: str, from_number: str):
    from .consent import normalize_phone
    integ = get_integration(practice, 'twilio')
    number = normalize_phone(from_number)
    if not number:
        raise IntegrationError('Enter the Twilio sending number in +1XXXXXXXXXX format.')
    secret = read_secret(integ)
    if account_sid:
        if not account_sid.startswith('AC') or len(account_sid) != 34:
            raise IntegrationError('The account SID starts with "AC" and is 34 characters long.')
        secret['account_sid'] = account_sid.strip()
    if auth_token:
        secret['auth_token'] = auth_token.strip()
    if not (secret.get('account_sid') and secret.get('auth_token')):
        raise IntegrationError('Enter the account SID and auth token.')
    try:
        resp = requests.get(f"https://api.twilio.com/2010-04-01/Accounts/{secret['account_sid']}.json",
                            auth=(secret['account_sid'], secret['auth_token']), timeout=TIMEOUT)
        ok = resp.status_code == 200
    except requests.RequestException:
        raise IntegrationError('Could not reach Twilio to check the credentials. Try again.')
    if not ok:
        raise IntegrationError('Twilio rejected these credentials.')
    write_secret(integ, secret)
    integ.config = {**(integ.config or {}), 'from_number': number}
    integ.connected_by = user
    mark(integ, 'connected')
    return integ


def twilio_disconnect(practice):
    integ = get_integration(practice, 'twilio')
    integ.secret, integ.config = '', {}
    mark(integ, 'not_connected')
