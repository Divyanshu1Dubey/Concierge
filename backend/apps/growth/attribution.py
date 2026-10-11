"""Classify where a website inquiry came from, using only the landing URL and the browser referrer."""
from urllib.parse import parse_qs, urlparse

SEARCH_ENGINES = ('com.google.android.googlequicksearchbox', 'google.', 'bing.com', 'duckduckgo.com', 'yahoo.', 'ecosia.org', 'search.brave.com', 'yandex.', 'baidu.com')
AI_ASSISTANTS = ('chatgpt.com', 'chat.openai.com', 'perplexity.ai', 'gemini.google.com', 'copilot.microsoft.com',
                 'claude.ai', 'you.com', 'phind.com', 'meta.ai')
SOCIAL = ('facebook.com', 'fb.com', 'instagram.com', 'l.instagram.com', 'lm.facebook.com', 't.co', 'twitter.com', 'x.com',
          'linkedin.com', 'lnkd.in', 'tiktok.com', 'youtube.com', 'pinterest.', 'nextdoor.com', 'reddit.com', 'threads.net')
EMAIL_HOSTS = ('mail.google.com', 'outlook.live.com', 'outlook.office.com', 'mail.yahoo.com', 'com.google.android.gm',
               'com.microsoft.office.outlook')
CLICK_IDS = ('gclid', 'gbraid', 'wbraid', 'fbclid', 'msclkid', 'ttclid')


def _host(value: str) -> str:
    try:
        host = (urlparse(value).hostname or '').lower()
    except ValueError:
        return ''
    return host[4:] if host.startswith('www.') else host


def _matches(host: str, patterns) -> bool:
    return any(host == p or host.endswith('.' + p) or (p.endswith('.') and (host.startswith(p) or ('.' + p) in host))
               for p in patterns)


def classify(url: str, referrer: str = '') -> dict:
    """Return attribution fields for a landing URL and referrer. Never raises on malformed input."""
    url = (url or '')[:2000]
    referrer = (referrer or '')[:2000]
    try:
        parsed = urlparse(url)
        params = {k.lower(): (v[0] if v else '') for k, v in parse_qs(parsed.query).items()}
        path = parsed.path or '/'
        page_host = _host(url)
    except ValueError:
        params, path, page_host = {}, '', ''

    utm_source = params.get('utm_source', '')[:100]
    utm_medium = params.get('utm_medium', '')[:100].lower()
    utm_campaign = params.get('utm_campaign', '')[:150]
    click_id = next((k for k in CLICK_IDS if params.get(k)), '')
    ref_host = _host(referrer)
    if ref_host and page_host and ref_host == page_host:
        ref_host = ''  # moving between pages of the same site is not a source

    source = utm_source.lower()
    if click_id in ('gclid', 'gbraid', 'wbraid') or (source == 'google' and utm_medium in ('cpc', 'ppc', 'paid', 'paidsearch')):
        channel = 'google_ads'
    elif click_id in ('fbclid', 'ttclid') and utm_medium in ('cpc', 'paid', 'paid_social', 'paidsocial') or \
            (utm_medium in ('paid_social', 'paidsocial')):
        channel = 'paid_social'
    elif 'gbp' in source or 'google_business' in source or 'gmb' in source or utm_campaign.lower() in ('gbp', 'gmb', 'google_business_profile'):
        channel = 'google_business'
    elif utm_medium == 'email' or source in ('newsletter', 'email') or _matches(ref_host, EMAIL_HOSTS):
        channel = 'email'
    elif _matches(ref_host, AI_ASSISTANTS) or source in ('chatgpt.com', 'chatgpt', 'perplexity', 'openai', 'gemini', 'copilot'):
        channel = 'ai_assistant'
    elif utm_source or utm_medium or utm_campaign:
        if utm_medium in ('social', 'social-media', 'organic_social'):
            channel = 'social'
        elif utm_medium in ('cpc', 'ppc', 'paid'):
            channel = 'google_ads' if 'google' in source else 'campaign'
        else:
            channel = 'campaign'
    elif _matches(ref_host, SEARCH_ENGINES):
        channel = 'organic_search'
    elif _matches(ref_host, SOCIAL):
        channel = 'social'
    elif ref_host:
        channel = 'referral'
    else:
        channel = 'direct'

    return {
        'channel': channel,
        'landing_path': path[:300],
        'referrer_host': ref_host[:200],
        'utm_source': utm_source,
        'utm_medium': utm_medium,
        'utm_campaign': utm_campaign,
        'has_click_id': bool(click_id),
    }


def record_attribution(conversation, url: str, referrer: str = ''):
    """Store attribution once per conversation (the first page the visitor started chatting on wins)."""
    from .models import InquiryAttribution
    if not conversation or not conversation.practice_id:
        return None
    existing = InquiryAttribution.objects.filter(conversation=conversation).first()
    if existing:
        return existing
    fields = classify(url, referrer)
    try:
        return InquiryAttribution.objects.create(practice_id=conversation.practice_id, conversation=conversation, **fields)
    except Exception:  # a concurrent init for the same conversation already stored it
        return InquiryAttribution.objects.filter(conversation=conversation).first()


def attribution_for_appointment(appointment) -> dict | None:
    conv_id = getattr(appointment, 'conversation_id', None)
    if not conv_id:
        return None
    from .models import InquiryAttribution
    att = InquiryAttribution.objects.filter(conversation_id=conv_id).first()
    if not att:
        return None
    return {
        'channel': att.channel,
        'channel_label': att.get_channel_display(),
        'landing_path': att.landing_path,
        'referrer_host': att.referrer_host,
        'utm_source': att.utm_source,
        'utm_medium': att.utm_medium,
        'utm_campaign': att.utm_campaign,
    }
