"""
One-click website visibility check.

Reads the practice's public homepage (and robots.txt / sitemap), compares what it finds with the facts the
practice approved in HeyJarvis, and returns a prioritised, plain-language fix list. Google's PageSpeed
Insights (Lighthouse) scores are added in the background when available.

Nothing here promises rankings or traffic: the checks cover accuracy, crawlability and conversion basics
that search engines and AI assistants rely on (Google: keep structured data consistent with visible text
and keep the Business Profile accurate).

Fetching is SSRF-safe: only http(s) on ports 80/443 to public IP addresses, every redirect is re-checked,
responses are size- and time-limited.
"""
import ipaddress
import json
import logging
import re
import socket
import threading
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
import requests.adapters
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_BYTES = 2_500_000
FETCH_TIMEOUT = 10
MAX_REDIRECTS = 4
USER_AGENT = 'HeyJarvisSiteCheck/1.0 (+practice website check requested by the practice)'
PSI_ENDPOINT = 'https://www.googleapis.com/pagespeedonline/v5/runPagespeed'
DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


class CheckError(Exception):
    pass


# ── Safe fetching ─────────────────────────────────────────────────────────────────────────────
#
# SSRF defence (DNS rebinding included): the hostname is resolved ONCE, every returned address must be
# globally routable, and the request is then sent to that exact IP. TLS still verifies the certificate
# against the original hostname (SNI + hostname check), and proxies from the environment are ignored,
# so a second DNS answer cannot redirect the connection. Every redirect hop repeats the whole process.

class _PinnedAdapter(requests.adapters.HTTPAdapter):
    """Send HTTPS to a pinned IP while presenting and verifying the original hostname."""

    def __init__(self, hostname, *a, **kw):
        self._hostname = hostname
        super().__init__(*a, **kw)

    def init_poolmanager(self, connections, maxsize, block=False, **kw):
        kw['server_hostname'] = self._hostname
        kw['assert_hostname'] = self._hostname
        super().init_poolmanager(connections, maxsize, block=block, **kw)


def _blocked_ip(ip) -> bool:
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.version == 6 and ip.sixtofour:
        ip = ip.sixtofour
    return not ip.is_global or ip.is_multicast or ip.is_reserved or ip.is_loopback or ip.is_link_local


def resolve_public(host: str) -> str:
    """Resolve once; refuse if ANY address is non-public. Returns the address to connect to."""
    try:
        literal = ipaddress.ip_address(host.strip('[]'))
    except ValueError:
        literal = None
    if literal is not None:
        if _blocked_ip(literal):
            raise CheckError('Only public websites can be checked.')
        return str(literal)
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise CheckError(f'The address "{host[:80]}" could not be found. Check the website address.')
    addrs = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split('%')[0])
        if _blocked_ip(ip):
            raise CheckError('Only public websites can be checked.')
        addrs.append(ip)
    if not addrs:
        raise CheckError('Only public websites can be checked.')
    v4 = [a for a in addrs if a.version == 4]
    return str((v4 or addrs)[0])


def _public_ip(host: str) -> bool:
    """Back-compat helper: True when the host resolves only to public addresses."""
    try:
        resolve_public(host)
        return True
    except CheckError as exc:
        if 'could not be found' in str(exc):
            raise
        return False


def _parse(url: str):
    url = (url or '').strip()
    if len(url) > 2000:
        raise CheckError('That website address is too long.')
    if url and '://' not in url:
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        raise CheckError('That website address is not valid.')
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise CheckError('Use a website address that starts with http:// or https://.')
    if parsed.username or parsed.password:
        raise CheckError('Website addresses with a username or password are not checked.')
    if port not in (None, 80, 443):
        raise CheckError('Only standard web ports are checked.')
    host = parsed.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.local', '.internal', '.localhost', '.home.arpa')) or \
            ('.' not in host and ':' not in host):
        raise CheckError('Only public websites can be checked.')
    return url, parsed, host


def validate_url(url: str) -> str:
    url, parsed, host = _parse(url)
    resolve_public(host)
    return url


def _pinned_request(url: str, timeout: int):
    url, parsed, host = _parse(url)
    ip = resolve_public(host)
    ip_host = f'[{ip}]' if ':' in ip else ip
    port = parsed.port
    netloc = ip_host + (f':{port}' if port else '')
    target = parsed._replace(netloc=netloc).geturl()
    host_header = host + (f':{port}' if port else '')
    session = requests.Session()
    session.trust_env = False  # never route through environment proxies (would bypass pinning)
    if parsed.scheme == 'https':
        session.mount('https://', _PinnedAdapter(host))
    headers = {'User-Agent': USER_AGENT, 'Accept': 'text/html,*/*;q=0.5', 'Host': host_header}
    return url, session, session.get(target, headers=headers, timeout=timeout, allow_redirects=False, stream=True)


def safe_get(url: str, max_bytes: int = MAX_BYTES, timeout: int = FETCH_TIMEOUT):
    """GET with pinned DNS and manual, re-validated redirects.
    Returns (final_url, status, headers, text, elapsed_ms, size_bytes)."""
    current = url
    started = time.monotonic()
    for _ in range(MAX_REDIRECTS + 1):
        if time.monotonic() - started > timeout * 2:
            raise CheckError('The website took too long to respond.')
        try:
            current, session, resp = _pinned_request(current, timeout)
        except CheckError:
            raise
        except requests.exceptions.SSLError:
            raise CheckError('The website has a security certificate problem, so browsers will warn visitors.')
        except requests.exceptions.Timeout:
            raise CheckError('The website took too long to respond.')
        except requests.RequestException:
            raise CheckError('The website did not respond. Check that it is online.')
        try:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get('Location', '')
                if not location:
                    break
                current = urljoin(current, location)
                continue
            chunks, size = [], 0
            deadline = started + timeout * 2
            for chunk in resp.iter_content(65536):
                size += len(chunk)
                if size > max_bytes or time.monotonic() > deadline:
                    break
                chunks.append(chunk)
            raw = b''.join(chunks)
            encoding = resp.encoding or 'utf-8'
            try:
                text = raw.decode(encoding, errors='replace')
            except LookupError:
                text = raw.decode('utf-8', errors='replace')
            return current, resp.status_code, dict(resp.headers), text, int((time.monotonic() - started) * 1000), size
        except requests.RequestException:
            raise CheckError('The website stopped responding while it was being read.')
        finally:
            resp.close()
            session.close()
    raise CheckError('The website redirects too many times.')


# ── HTML parsing ──────────────────────────────────────────────────────────────────────────────

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.meta = {}
        self.lang = ''
        self.canonical = ''
        self.h1 = []
        self.links = []
        self.scripts = []
        self.ld_json = []
        self.images = 0
        self.images_with_alt = 0
        self.text_parts = []
        self.forms = 0
        self.buttons = []
        self._in = []
        self._buf = ''

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or '') for k, v in attrs}
        if tag == 'html':
            self.lang = a.get('lang', '')
        elif tag == 'meta':
            key = (a.get('name') or a.get('property') or '').lower()
            if key:
                self.meta[key] = a.get('content', '')
        elif tag == 'link' and 'canonical' in a.get('rel', '').lower():
            self.canonical = a.get('href', '')
        elif tag == 'a':
            self.links.append(a.get('href', ''))
            self._in.append('a')
            self._buf = ''
        elif tag == 'script':
            if a.get('src'):
                self.scripts.append(a.get('src') + ' ' + ' '.join(f'{k}={v}' for k, v in a.items() if k.startswith('data-')))
            self._in.append('ldjson' if 'ld+json' in a.get('type', '').lower() else 'script')
            self._buf = ''
        elif tag == 'style':
            self._in.append('style')
        elif tag in ('title', 'h1', 'button'):
            self._in.append(tag)
            self._buf = ''
        elif tag == 'img':
            self.images += 1
            if a.get('alt', '').strip():
                self.images_with_alt += 1
        elif tag == 'form':
            self.forms += 1

    def handle_endtag(self, tag):
        if not self._in:
            return
        top = self._in[-1]
        if (tag == 'script' and top in ('script', 'ldjson')) or tag == top or (tag == 'a' and top == 'a'):
            self._in.pop()
            text = self._buf.strip()
            if top == 'title':
                self.title = text
            elif top == 'h1':
                self.h1.append(text)
            elif top == 'ldjson':
                self.ld_json.append(text)
            elif top in ('button', 'a') and text:
                self.buttons.append(text[:80])
            self._buf = ''

    def handle_data(self, data):
        top = self._in[-1] if self._in else ''
        if top in ('script', 'style'):
            return
        if top in ('title', 'h1', 'ldjson', 'button', 'a'):
            self._buf += data
        if top != 'ldjson' and len(self.text_parts) < 4000:
            self.text_parts.append(data)

    @property
    def text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.text_parts))


def _ld_items(blocks):
    items = []
    for raw in blocks:
        try:
            data = json.loads(raw)
        except ValueError:
            items.append({'@invalid': True})
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if '@graph' in node and isinstance(node['@graph'], list):
                    stack.extend(node['@graph'])
                items.append(node)
    return items


def _types(item):
    t = item.get('@type', [])
    return [x.lower() for x in (t if isinstance(t, list) else [t]) if isinstance(x, str)]


LOCAL_TYPES = {'dentist', 'localbusiness', 'medicalbusiness', 'medicalclinic', 'medicalorganization', 'healthandbeautybusiness', 'physician'}


# ── Practice facts ────────────────────────────────────────────────────────────────────────────

def practice_facts(practice) -> dict:
    rules = getattr(practice, 'booking_rules', None)
    hours = (rules.business_hours if rules else None) or {}
    open_days = [d for d in DAYS if isinstance(hours.get(d), dict) and not hours[d].get('closed')]
    return {
        'name': practice.name,
        'phone_digits': re.sub(r'\D', '', practice.phone or '')[-10:],
        'phone': practice.phone,
        'street': (practice.address or '').strip(),
        'zip': (practice.zip_code or '').strip(),
        'city': (practice.city or '').strip(),
        'state': (practice.state or '').strip(),
        'website': practice.website,
        'hours': {d: hours.get(d) for d in DAYS if isinstance(hours.get(d), dict)},
        'open_days': open_days,
        'api_key': practice.api_key,
    }


def _finding(fid, ok, severity, category, title, detail, fix, warn=False):
    return {'id': fid, 'status': 'pass' if ok else ('warn' if warn else 'fail'), 'severity': severity,
            'category': category, 'title': title, 'detail': detail, 'fix': '' if ok else fix}


def analyze(practice, url: str, html: str, final_url: str, status: int, elapsed_ms: int, size: int,
            robots_txt: str = '', sitemap_found=None) -> list:
    facts = practice_facts(practice)
    p = PageParser()
    try:
        p.feed(html)
    except Exception:
        pass
    text = p.text
    lower = text.lower()
    digits_text = re.sub(r'\D', '', text + ' ' + ' '.join(h for h in p.links if h.lower().startswith('tel:')))
    items = _ld_items(p.ld_json)
    local_items = [i for i in items if LOCAL_TYPES & set(_types(i))]
    f = []

    # Facts patients rely on
    name_ok = facts['name'].lower() in lower or facts['name'].lower() in p.title.lower()
    f.append(_finding('name', name_ok, 'medium', 'facts', 'Practice name appears on the page',
                      f'Looking for "{facts["name"]}".',
                      'Show your practice name exactly as it appears on your Google Business Profile.'))
    if facts['phone_digits']:
        phone_ok = facts['phone_digits'] in digits_text
        f.append(_finding('phone', phone_ok, 'high', 'facts', 'Phone number matches your HeyJarvis settings',
                          f'Expected {facts["phone"]}.',
                          'Put the same phone number on your homepage (ideally as a tap-to-call link) and in HeyJarvis.'))
        tel_ok = any(h.lower().startswith('tel:') for h in p.links)
        f.append(_finding('tel_link', tel_ok, 'medium', 'conversion', 'Tap-to-call link for mobile visitors',
                          'Most dental searches happen on phones.',
                          'Make your phone number a link: <a href="tel:+1XXXXXXXXXX">.'))
    if facts['zip'] or facts['street']:
        street_key = facts['street'].split(',')[0].lower()[:25] if facts['street'] else ''
        addr_ok = (facts['zip'] and facts['zip'] in text) or (street_key and street_key in lower)
        f.append(_finding('address', bool(addr_ok), 'high', 'facts', 'Address matches your HeyJarvis settings',
                          f'Expected {facts["street"]}, {facts["city"]} {facts["zip"]}.',
                          'Show your full street address on the homepage or footer, matching Google and HeyJarvis.'))
    if facts['open_days']:
        day_hits = sum(1 for d in DAYS if d in lower or d[:3] + ' ' in lower)
        hours_ok = 'hour' in lower and day_hits >= 2
        f.append(_finding('hours', hours_ok, 'medium', 'facts', 'Office hours are listed',
                          'Patients and search engines look for opening hours.',
                          'Add your weekly hours (the same ones set in HeyJarvis Hours & Services).'))

    # Conversion
    widget_ok = any(('widget.js' in s or 'heyjarvis' in s.lower()) for s in p.scripts)
    key_ok = bool(facts['api_key']) and any(facts['api_key'] in s for s in p.scripts)
    f.append(_finding('widget', widget_ok, 'high', 'conversion', 'HeyJarvis chat is installed',
                      'The chat captures after-hours visitors.' + (' Script found but with a different practice key.' if widget_ok and not key_ok else ''),
                      'Paste your embed code from Plugin & Embed Code before </body>, or install the WordPress plugin.',
                      warn=widget_ok and not key_ok))
    cta_words = ('book', 'appointment', 'schedule', 'request a visit', 'new patient')
    cta_ok = any(any(w in b.lower() for w in cta_words) for b in p.buttons) or p.forms > 0
    f.append(_finding('cta', cta_ok, 'medium', 'conversion', 'Clear "book an appointment" button',
                      'Visitors should see how to book without scrolling.',
                      'Add a visible "Request an appointment" button near the top of the page.'))

    # Search basics
    t_len = len(p.title)
    f.append(_finding('title', 10 <= t_len <= 65, 'medium', 'search', 'Page title is descriptive',
                      f'Title: "{p.title[:90]}"' if p.title else 'No title found.',
                      'Use a title like "Family Dentist in {city} | {practice}" (under about 60 characters).'
                      .replace('{city}', facts['city'] or 'your city').replace('{practice}', facts['name']),
                      warn=bool(p.title)))
    desc = p.meta.get('description', '')
    f.append(_finding('description', 50 <= len(desc) <= 170, 'low', 'search', 'Meta description summarises the practice',
                      f'{len(desc)} characters.' if desc else 'No meta description found.',
                      'Write a one-sentence summary (about 150 characters) mentioning your services and city.',
                      warn=bool(desc)))
    f.append(_finding('h1', len(p.h1) >= 1, 'low', 'search', 'Page has a main heading',
                      f'Found {len(p.h1)} main heading(s).', 'Add one clear main heading (H1) describing your practice.'))
    robots_meta = (p.meta.get('robots', '') + ' ' + p.meta.get('googlebot', '')).lower()
    noindex = 'noindex' in robots_meta
    f.append(_finding('indexable', not noindex, 'high', 'search', 'Page can appear in search results',
                      'A "noindex" tag hides the page from Google.' if noindex else 'No noindex tag found.',
                      'Remove the noindex robots tag (often left on by a website builder or staging setting).'))
    blocked = _robots_blocks_all(robots_txt)
    f.append(_finding('robots', not blocked, 'high', 'search', 'robots.txt allows search engines',
                      'robots.txt blocks all crawlers.' if blocked else 'Crawlers are allowed.',
                      'Edit robots.txt so it does not contain "Disallow: /" for all user agents.'))
    if sitemap_found is not None:
        f.append(_finding('sitemap', bool(sitemap_found), 'low', 'search', 'Sitemap is available',
                          'Helps search engines find every page.', 'Publish a sitemap.xml (most website builders can generate one).'))

    # Structured data / AI readiness
    f.append(_finding('schema_local', bool(local_items), 'medium', 'ai', 'Structured data identifies you as a dental practice',
                      f'Found: {", ".join(sorted({t for i in local_items for t in _types(i)}))}.' if local_items
                      else 'No Dentist / LocalBusiness structured data found.',
                      'Add Dentist structured data. HeyJarvis generates it from your approved facts (see "Website facts" below).'))
    if any(i.get('@invalid') for i in items):
        f.append(_finding('schema_valid', False, 'medium', 'ai', 'Structured data is valid JSON',
                          'A structured data block could not be read.', 'Fix the JSON-LD block (test it with Google\'s Rich Results Test).'))
    if local_items and facts['phone_digits']:
        tel = re.sub(r'\D', '', str(local_items[0].get('telephone', '')))[-10:]
        f.append(_finding('schema_phone', not tel or tel == facts['phone_digits'], 'medium', 'ai',
                          'Structured data phone matches', f'Structured data phone: {local_items[0].get("telephone", "none")}.',
                          'Update the telephone in your structured data to match your real phone number.'))

    # Technical
    https_ok = final_url.startswith('https://')
    f.append(_finding('https', https_ok, 'high', 'technical', 'Secure connection (HTTPS)', f'Final address: {final_url[:120]}',
                      'Turn on HTTPS with your web host; browsers label plain HTTP sites "Not secure".'))
    f.append(_finding('viewport', 'viewport' in p.meta, 'medium', 'technical', 'Mobile-friendly layout tag',
                      'The viewport tag lets the page fit phone screens.',
                      'Add <meta name="viewport" content="width=device-width, initial-scale=1">.'))
    f.append(_finding('speed', elapsed_ms <= 2500, 'medium', 'technical', 'Server responds quickly',
                      f'Homepage responded in {elapsed_ms / 1000:.1f}s ({max(1, round(size / 1024))} KB).',
                      'Ask your web host about caching or a faster plan; slow pages lose mobile visitors.',
                      warn=elapsed_ms <= 5000))
    if p.images:
        ratio = p.images_with_alt / p.images
        f.append(_finding('alt', ratio >= 0.8, 'low', 'technical', 'Images have descriptions (alt text)',
                          f'{p.images_with_alt} of {p.images} images have alt text.',
                          'Describe meaningful images (e.g. "Dr. Lee with a patient") for accessibility and search.'))
    f.append(_finding('lang', bool(p.lang), 'low', 'technical', 'Page language is declared',
                      f'lang="{p.lang}"' if p.lang else 'No language attribute.', 'Add lang="en" to the <html> tag.'))
    if status >= 400:
        f.insert(0, _finding('status', False, 'high', 'technical', 'Homepage loads', f'The site returned HTTP {status}.',
                             'Fix the homepage error with your web host.'))
    return f


def _robots_blocks_all(robots: str) -> bool:
    agent_all, blocked = False, False
    for line in (robots or '').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line or ':' not in line:
            continue
        key, value = [x.strip() for x in line.split(':', 1)]
        key = key.lower()
        if key == 'user-agent':
            agent_all = value == '*'
        elif key == 'disallow' and agent_all and value == '/':
            blocked = True
        elif key == 'allow' and agent_all and value == '/':
            blocked = False
    return blocked


SEVERITY_WEIGHT = {'high': 3, 'medium': 2, 'low': 1}


def score(findings) -> int:
    total = sum(SEVERITY_WEIGHT[x['severity']] for x in findings)
    got = sum(SEVERITY_WEIGHT[x['severity']] * (1 if x['status'] == 'pass' else 0.5 if x['status'] == 'warn' else 0)
              for x in findings)
    return round(100 * got / total) if total else 0


def order_findings(findings):
    rank = {'fail': 0, 'warn': 1, 'pass': 2}
    return sorted(findings, key=lambda x: (rank[x['status']], -SEVERITY_WEIGHT[x['severity']]))


# ── Run a check ───────────────────────────────────────────────────────────────────────────────

def run_check(practice, url: str, user=None, with_pagespeed=True):
    """Run the fast HTML checks now (stored immediately); Lighthouse scores follow in the background."""
    from .models import VisibilityReport
    started = time.monotonic()
    report = VisibilityReport(practice=practice, url=(url or practice.website or '')[:500], requested_by=user)
    try:
        final_url, status, headers, html, elapsed, size = safe_get(report.url)
        report.url = final_url[:500]
        origin = '{0.scheme}://{0.netloc}'.format(urlparse(final_url))
        robots_txt, sitemap_found = '', None
        try:
            _, r_status, _, robots_txt, _, _ = safe_get(origin + '/robots.txt', max_bytes=200_000, timeout=6)
            if r_status >= 400:
                robots_txt = ''
            sitemap_found = 'sitemap:' in robots_txt.lower()
            if not sitemap_found:
                _, s_status, _, s_text, _, _ = safe_get(origin + '/sitemap.xml', max_bytes=200_000, timeout=6)
                sitemap_found = s_status < 400 and ('<urlset' in s_text or '<sitemapindex' in s_text)
        except CheckError:
            pass
        findings = analyze(practice, report.url, html, final_url, status, elapsed, size, robots_txt, sitemap_found)
        report.findings = order_findings(findings)
        report.score = score(findings)
        report.status = 'ok'
    except CheckError as exc:
        report.status, report.error = 'failed', str(exc)[:300]
    report.facts = {k: v for k, v in practice_facts(practice).items() if k != 'api_key'}
    report.duration_ms = int((time.monotonic() - started) * 1000)
    report.lighthouse = {'status': 'pending' if (with_pagespeed and report.status == 'ok' and pagespeed_enabled()) else 'off'}
    report.save()
    if report.lighthouse['status'] == 'pending':
        _start_pagespeed(report.id)
    return report


def pagespeed_enabled() -> bool:
    return bool(getattr(settings, 'PAGESPEED_API_KEY', '')) or bool(getattr(settings, 'PAGESPEED_ENABLED', False))


def fetch_pagespeed(url: str) -> dict:
    params = [('url', url), ('strategy', 'mobile')]
    for cat in ('performance', 'accessibility', 'best-practices', 'seo'):
        params.append(('category', cat))
    key = getattr(settings, 'PAGESPEED_API_KEY', '')
    if key:
        params.append(('key', key))
    resp = requests.get(PSI_ENDPOINT, params=params, timeout=55)
    if resp.status_code != 200:
        try:
            message = resp.json().get('error', {}).get('message', '')
        except ValueError:
            message = ''
        raise CheckError(f'Google PageSpeed could not test the page ({resp.status_code}). {message[:120]}'.strip())
    data = resp.json().get('lighthouseResult', {})
    cats = data.get('categories', {})
    audits = data.get('audits', {})
    out = {'status': 'ok', 'strategy': 'mobile', 'checked_at': timezone.now().isoformat()}
    for key_name, cat in cats.items():
        if cat.get('score') is not None:
            out[key_name.replace('-', '_')] = round(cat['score'] * 100)
    for audit in ('largest-contentful-paint', 'cumulative-layout-shift', 'total-blocking-time'):
        if audits.get(audit, {}).get('displayValue'):
            out[audit.replace('-', '_')] = audits[audit]['displayValue']
    return out


def _start_pagespeed(report_id):
    def work():
        from django.db import close_old_connections
        from .models import VisibilityReport
        try:
            report = VisibilityReport.objects.filter(id=report_id).first()
            if not report:
                return
            try:
                report.lighthouse = fetch_pagespeed(report.url)
            except (CheckError, requests.RequestException, ValueError) as exc:
                report.lighthouse = {'status': 'failed',
                                     'error': str(exc)[:200] if isinstance(exc, CheckError) else 'Google PageSpeed did not respond in time.'}
            report.save(update_fields=['lighthouse'])
        finally:
            close_old_connections()
    if getattr(settings, 'GROWTH_SYNC_BACKGROUND', False):
        work()
    else:
        threading.Thread(target=work, daemon=True).start()


# ── Website facts export (FAQ + structured data from approved facts) ───────────────────────────

def facts_export(practice, request=None) -> dict:
    from django.utils.html import escape
    from apps.practices.branding import social_links
    from apps.practices.models import KnowledgeEntry
    facts = practice_facts(practice)
    ld = {
        '@context': 'https://schema.org',
        '@type': 'Dentist',
        'name': practice.name,
    }
    if practice.website:
        ld['url'] = practice.website
    if practice.phone:
        ld['telephone'] = practice.phone
    if facts['street']:
        ld['address'] = {'@type': 'PostalAddress', 'streetAddress': facts['street'], 'addressLocality': facts['city'],
                         'addressRegion': facts['state'], 'postalCode': facts['zip'], 'addressCountry': 'US'}
    specs = []
    for day, cfg in facts['hours'].items():
        if cfg and not cfg.get('closed') and cfg.get('open') and cfg.get('close'):
            specs.append({'@type': 'OpeningHoursSpecification', 'dayOfWeek': day.title(),
                          'opens': str(cfg['open'])[:5], 'closes': str(cfg['close'])[:5]})
    if specs:
        ld['openingHoursSpecification'] = specs
    same_as = [v for k, v in social_links(practice).items() if k != 'website']
    if same_as:
        ld['sameAs'] = same_as
    logo = practice.brand_assets.filter(kind='logo').order_by('-created_at').first()
    if logo:
        from apps.practices.branding import asset_url
        ld['logo'] = asset_url(logo, request)

    entries = list(KnowledgeEntry.objects.filter(practice=practice, is_active=True)
                   .exclude(category='doctor').order_by('category', 'title')[:20])
    faq_ld = None
    faq_html = ''
    if entries:
        faq_ld = {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
            {'@type': 'Question', 'name': e.title, 'acceptedAnswer': {'@type': 'Answer', 'text': e.content}}
            for e in entries]}
        parts = ['<section class="practice-faq">', f'  <h2>Frequently asked questions</h2>']
        for e in entries:
            parts.append(f'  <h3>{escape(e.title)}</h3>\n  <p>{escape(e.content)}</p>')
        parts.append('</section>')
        faq_html = '\n'.join(parts)

    def script(obj):
        return '<script type="application/ld+json">\n' + json.dumps(obj, indent=2, ensure_ascii=False).replace('</', '<\\/') + '\n</script>'

    return {
        'structured_data': script(ld),
        'faq_structured_data': script(faq_ld) if faq_ld else '',
        'faq_html': faq_html,
        'faq_count': len(entries),
        'notes': [
            'Everything here comes from facts your practice approved in HeyJarvis. Update them there, then copy again.',
            'Paste the structured data into your site header (or use a structured-data plugin). Test it with Google\'s Rich Results Test.',
            'Search engines decide whether to show rich results; this markup helps them read your facts but does not guarantee placement.',
        ],
    }


# ── Installation check ────────────────────────────────────────────────────────────────────────

class _ScriptTags(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.scripts.append({k.lower(): (v or '') for k, v in attrs})


def install_check(practice, url: str) -> dict:
    """Is the HeyJarvis chat really installed on this page, with this practice's key and an allowed domain?"""
    from apps.core.security import is_allowed_origin
    target = (url or practice.website or '').strip()
    if not target:
        raise CheckError('Add your website address in Practice Settings first.')
    final_url, status, _headers, html, _ms, _size = safe_get(target)
    parser = _ScriptTags()
    try:
        parser.feed(html)
    except Exception:
        pass
    ours = [s for s in parser.scripts if 'widget.js' in s.get('src', '') or 'heyjarvis' in s.get('src', '').lower()
            or any(k.startswith('data-heyjarvis') for k in s)]
    origin = '{0.scheme}://{0.netloc}'.format(urlparse(final_url))
    checks = []

    def add(key, ok, label, detail, fix=''):
        checks.append({'key': key, 'ok': bool(ok), 'label': label, 'detail': detail, 'fix': '' if ok else fix})

    add('page', status < 400, 'Website page loads', f'{final_url} returned HTTP {status}.', 'Fix the page error with your web host.')
    add('script', bool(ours), 'Chat script is on the page',
        f'Found {len(ours)} HeyJarvis script tag(s).' if ours else 'No HeyJarvis script tag found in the page HTML.',
        'Paste the embed code from this page before </body>, or activate the WordPress plugin. If you used Google Tag '
        'Manager, the script is added by JavaScript and cannot be seen here; open your site and look for the chat button.')
    if ours:
        tag = ours[0]
        key = tag.get('data-heyjarvis-client') or tag.get('data-client-key') or tag.get('data-key') or ''
        slug = tag.get('data-practice', '')
        key_ok = (key and key == practice.api_key) or (not key and slug and slug == practice.slug)
        add('key', key_ok, 'Script belongs to this practice',
            'The client key matches.' if key_ok else ('The script uses a different practice key.' if key else 'The script has no client key.'),
            'Copy the embed code again from this page; the key may have been regenerated.')
        api = tag.get('data-api-url') or tag.get('src', '').rsplit('/widget.js', 1)[0]
        public = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
        api_host = (urlparse(api).hostname or '').lower() if api.startswith('http') else ''
        own_host = (urlparse(public).hostname or '').lower() if public else ''
        api_ok = bool(api_host) and (not own_host or api_host == own_host)
        add('server', api_ok, 'Script points to this HeyJarvis server',
            f'Script loads from {api_host or "an unknown address"}.',
            f'Use the embed code from this page so the script loads from {own_host or "your HeyJarvis address"}.')
    domains = practice.allowed_domains_list
    allowed = is_allowed_origin(origin, domains) if domains else True
    add('domain', allowed, 'Website address is allowed to use the chat',
        f'{urlparse(final_url).hostname} is ' + ('allowed.' if domains and allowed else 'not on the allowed list.' if not allowed
                                                else 'allowed (no domain list set, so any site can use this key).'),
        f'Add {urlparse(final_url).hostname} under Allowed domains on this page.')
    return {'url': final_url, 'installed': all(c['ok'] for c in checks), 'checks': checks,
            'checked_at': timezone.now().isoformat()}
