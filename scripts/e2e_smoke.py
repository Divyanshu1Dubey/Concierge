"""Headless browser smoke test against a LOCAL dev server with demo accounts enabled.

Usage (from backend/, dev settings, throwaway database):
    python manage.py migrate && python manage.py seed_raleigh
    python manage.py runserver 127.0.0.1:8010
    python ../scripts/e2e_smoke.py        # requires `pip install playwright && playwright install chromium`

Never point this at production: it logs in with demo accounts and writes test data.
"""
import sys
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8010'
PAGES = [
    '/dashboard', '/dashboard/requests', '/dashboard/conversations', '/dashboard/leads',
    '/dashboard/patients', '/dashboard/email', '/dashboard/concierge', '/dashboard/installation',
    '/dashboard/widget-settings', '/dashboard/business-rules', '/dashboard/email-settings',
    '/dashboard/templates', '/dashboard/team', '/dashboard/security', '/dashboard/settings',
    '/dashboard/practices',
]
results = []
failures = []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    if not cond:
        failures.append(name)


def attach(page, bucket):
    page.on('console', lambda m: m.type == 'error' and bucket['console'].append(m.text))
    page.on('pageerror', lambda e: bucket['console'].append(f'pageerror: {e}'))
    page.on('response', lambda r: ('/api/' in r.url and r.status >= 400) and bucket['http'].append(f'{r.status} {r.request.method} {r.url}'))


ACCOUNTS = {
    'Agency Admin': 'admin@raleighdentistry.com',
    'Doctor (Practice Admin)': 'doctor@raleighdentistry.com',
    'Front Desk': 'desk@raleighdentistry.com',
}


def login(page, label):
    """Sign in through the real form. Test password comes from E2E_PASSWORD (never hardcoded)."""
    import os
    password = os.environ.get('E2E_PASSWORD')
    if not password:
        raise SystemExit('Set E2E_PASSWORD to the local test accounts\' password.')
    page.goto(f'{BASE}/login')
    page.get_by_label('Email').fill(ACCOUNTS[label])
    page.locator('#login-password').fill(password)
    page.get_by_role('button', name='Sign in').click()
    page.wait_for_url('**/dashboard', timeout=15000)
    page.wait_for_load_state('networkidle')


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ---------------- Practice admin (doctor) ----------------
    ctx = browser.new_context()
    page = ctx.new_page()
    bucket = {'console': [], 'http': []}
    attach(page, bucket)
    login(page, 'Doctor (Practice Admin)')
    check('doctor login lands on dashboard', page.url.endswith('/dashboard'))

    for path in PAGES:
        bucket['console'].clear(); bucket['http'].clear()
        page.goto(BASE + path)
        page.wait_for_load_state('networkidle')
        body = page.inner_text('body')
        crashed = 'Something went wrong' in body or len(body.strip()) < 30
        if path == '/dashboard/practices':
            check(f'{path}: practice admin redirected away', not page.url.endswith('/practices'), page.url)
            continue
        check(f'{path}: renders, no console errors, no failed API calls',
              not crashed and not bucket['console'] and not bucket['http'],
              '; '.join(bucket['console'][:3] + bucket['http'][:3]))

    # Settings persistence through the real UI
    page.goto(BASE + '/dashboard/widget-settings')
    page.wait_for_load_state('networkidle')
    title_input = page.locator('input[type=text]').first
    title_input.fill('QA Concierge Title')
    page.get_by_role('button', name='Save Settings').click()
    page.wait_for_timeout(1500)
    page.reload(); page.wait_for_load_state('networkidle')
    check('widget title persists after reload', page.locator('input[type=text]').first.input_value() == 'QA Concierge Title')

    page.goto(BASE + '/dashboard/business-rules')
    page.wait_for_load_state('networkidle')
    page.get_by_role('button', name='Save Rules').click()
    page.wait_for_timeout(1500)
    check('business rules save shows success toast', page.get_by_text('Business rules saved').count() > 0)

    page.goto(BASE + '/dashboard/templates')
    page.wait_for_load_state('networkidle')
    page.locator('input[type=text]').first.fill('Thanks {{patient_name}}')
    page.locator('textarea').first.fill('Hi {{patient_name}}, we received your request. - {{practice}}')
    page.get_by_role('button', name='Save Template').click()
    page.wait_for_timeout(1500)
    page.reload(); page.wait_for_load_state('networkidle')
    check('template created and persists', page.locator('input[type=text]').first.input_value() == 'Thanks {{patient_name}}')

    page.goto(BASE + '/dashboard/team')
    page.wait_for_load_state('networkidle')
    check('team page lists seeded staff', page.get_by_text('desk@raleighdentistry.com').count() > 0)

    # Concierge preview creates a real request in this practice
    page.goto(BASE + '/dashboard/concierge')
    page.wait_for_load_state('networkidle')
    chat_input = page.locator('input[type=text]').last
    for msg in ['I have a dental emergency', 'Jane QA', '919-555-0100']:
        chat_input.fill(msg)
        chat_input.press('Enter')
        page.wait_for_timeout(1500)
    check('concierge chat replied (no delivery error)', page.get_by_text('Message not delivered').count() == 0)
    page.goto(BASE + '/dashboard/requests')
    page.wait_for_load_state('networkidle')
    check('emergency chat produced a request in the inbox', page.get_by_text('Jane QA').count() > 0)

    # Logout revokes and returns to login
    refresh = page.evaluate("localStorage.getItem('auth_refresh')")
    page.get_by_title('Sign out of HeyJarvis').click()
    page.wait_for_url('**/login', timeout=10000)
    page.wait_for_timeout(800)
    r = page.request.post(f'{BASE}/api/auth/token/refresh/', data={'refresh': refresh})
    check('logout revoked refresh token (refresh -> 401)', r.status == 401, str(r.status))
    page.goto(BASE + '/dashboard/team')
    try:
        page.wait_for_url('**/login', timeout=5000)
    except Exception:
        pass
    check('protected page after logout redirects to login', '/login' in page.url)
    ctx.close()

    # ---------------- Front desk ----------------
    ctx = browser.new_context()
    page = ctx.new_page()
    bucket = {'console': [], 'http': []}
    attach(page, bucket)
    login(page, 'Front Desk')
    page.goto(BASE + '/dashboard/team')
    page.wait_for_load_state('networkidle')
    check('front desk redirected away from Team', not page.url.endswith('/team'), page.url)
    for path in ['/dashboard', '/dashboard/requests', '/dashboard/conversations', '/dashboard/email']:
        bucket['console'].clear(); bucket['http'].clear()
        page.goto(BASE + path); page.wait_for_load_state('networkidle')
        check(f'front desk {path}: no errors', not bucket['console'] and not bucket['http'],
              '; '.join(bucket['console'][:3] + bucket['http'][:3]))
    token = page.evaluate("localStorage.getItem('auth_token')")
    r = page.request.put(f'{BASE}/api/practices/settings/', data={'widget_title': 'x'}, headers={'Authorization': f'Bearer {token}'})
    check('front desk API settings write -> 403', r.status == 403, str(r.status))
    ctx.close()

    # ---------------- Agency admin ----------------
    ctx = browser.new_context()
    page = ctx.new_page()
    bucket = {'console': [], 'http': []}
    attach(page, bucket)
    login(page, 'Agency Admin')
    page.goto(BASE + '/dashboard/practices'); page.wait_for_load_state('networkidle')
    check('agency practices page: no errors', not bucket['console'] and not bucket['http'],
          '; '.join(bucket['console'][:3] + bucket['http'][:3]))
    ctx.close()

    # ---------------- Hosted concierge (public) ----------------
    ctx = browser.new_context()
    page = ctx.new_page()
    bucket = {'console': [], 'http': []}
    attach(page, bucket)
    page.goto(BASE + '/concierge/raleigh-dentistry'); page.wait_for_load_state('networkidle')
    check('hosted concierge loads without errors', page.get_by_text('not found').count() == 0 and not bucket['http'],
          '; '.join(bucket['http'][:3]))
    browser.close()

for name, ok, detail in results:
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))
print(f'\n{len(results) - len(failures)}/{len(results)} passed')
sys.exit(1 if failures else 0)
