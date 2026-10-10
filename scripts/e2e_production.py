"""Browser checks for the production login page, access requests and reply UI (LOCAL dev server only).

Run against a server on a throwaway DB copy with console email and AI off, e.g. port 8010.
Set E2E_PASSWORD to the local test accounts' password. Never run against production.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get('E2E_BASE', 'http://127.0.0.1:8010')
results, failures = [], []
ACCOUNTS = {
    'Agency Admin': 'admin@raleighdentistry.com',
    'Front Desk': 'desk@raleighdentistry.com',
}


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    if not cond:
        failures.append(name)


def login(page, label):
    password = os.environ.get('E2E_PASSWORD')
    if not password:
        raise SystemExit('Set E2E_PASSWORD.')
    page.goto(f'{BASE}/login')
    page.get_by_label('Email').fill(ACCOUNTS[label])
    page.locator('#login-password').fill(password)
    page.get_by_role('button', name='Sign in').click()
    page.wait_for_url('**/dashboard', timeout=15000)
    page.wait_for_load_state('networkidle')


def overflow(page):
    return page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')


with sync_playwright() as p:
    browser = p.chromium.launch()
    errors = []

    # 1. Public login page: no demo panel, no credentials anywhere public.
    page = browser.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(f'{BASE}/login')
    page.wait_for_load_state('networkidle')
    html = page.content()
    check('login: no "Demo environment" panel', 'Demo environment' not in html)
    check('login: no demo account emails in page', 'raleighdentistry.com' not in html)
    cfg = page.request.get(f'{BASE}/api/auth/config/').text()
    check('auth config API exposes no accounts/passwords', 'password' not in cfg.lower() and 'raleighdentistry' not in cfg)
    pw = page.locator('#login-password')
    page.get_by_role('button', name='Show password').click()
    check('password toggle reveals text', pw.get_attribute('type') == 'text')
    page.get_by_role('button', name='Hide password').click()
    check('password toggle hides text again', pw.get_attribute('type') == 'password')
    page.get_by_role('button', name='Sign in').click()
    check('empty submit shows validation error', page.get_by_text('Enter your email and password.').count() > 0)
    page.get_by_label('Email').fill('nobody@example.test')
    pw.fill('wrong-password-123')
    page.get_by_role('button', name='Sign in').click()
    try:
        page.get_by_text('Invalid email or password').wait_for(timeout=10000)
        bad_login_msg = True
    except Exception:
        bad_login_msg = False
    check('wrong credentials show an error', bad_login_msg)
    check('forgot-password link present', page.get_by_role('link', name='Forgot password?').count() > 0)

    # 2. Request access: real form, validation, stored for agency review.
    page.get_by_role('link', name='Request access for your practice').click()
    page.wait_for_url('**/request-access')
    page.get_by_role('button', name='Send request').click()
    page.wait_for_timeout(800)
    check('request access: required-field errors shown', page.get_by_text('This field is required.').count() >= 2)
    tag = str(int(time.time()))[-6:]
    page.get_by_label('Practice name').fill(f'Synthetic Oak Dental {tag}')
    page.get_by_label('Your name').fill('Dr. Synthetic Oak')
    page.get_by_label('Work email').fill(f'oak-{tag}@example.test')
    page.get_by_role('button', name='Send request').click()
    page.wait_for_timeout(1200)
    check('request access: confirmation shown', page.get_by_role('heading', name='Request received').count() > 0)
    page.close()

    # 3. Phone width layouts.
    m = browser.new_page(viewport={'width': 390, 'height': 844})
    for path in ['/login', '/request-access']:
        m.goto(BASE + path)
        m.wait_for_load_state('networkidle')
        check(f'390px {path}: no horizontal scroll', overflow(m) <= 1, f'{overflow(m)}px')
    m.close()

    # 4. Agency admin reviews the request and starts onboarding from it.
    ctx = browser.new_context()
    a = ctx.new_page()
    a.on('pageerror', lambda e: errors.append(str(e)))
    login(a, 'Agency Admin')
    a.goto(f'{BASE}/dashboard/practices')
    a.wait_for_load_state('networkidle')
    check('agency: access request listed', a.get_by_text(f'Synthetic Oak Dental {tag}').count() > 0)
    row = a.locator('li', has_text=f'Synthetic Oak Dental {tag}')
    row.get_by_role('button', name='Start onboarding').click()
    a.wait_for_timeout(500)
    check('agency: onboarding form prefilled from request',
          a.locator(f'input[value="Synthetic Oak Dental {tag}"]').count() > 0)
    a.keyboard.press('Escape')
    ctx.close()

    # 5. Front desk: cannot see agency pages or access requests; email history + reply check honest.
    ctx = browser.new_context()
    d = ctx.new_page()
    d.on('pageerror', lambda e: errors.append(str(e)))
    login(d, 'Front Desk')
    token = d.evaluate("localStorage.getItem('auth_token')")
    r = d.request.get(f'{BASE}/api/practices/access-requests/', headers={'Authorization': f'Bearer {token}'})
    check('front desk API: access requests forbidden', r.status == 403, str(r.status))
    d.goto(f'{BASE}/dashboard/practices')
    d.wait_for_load_state('networkidle')
    check('front desk: agency practices page not shown', d.get_by_text('Access requests').count() == 0)
    d.goto(f'{BASE}/dashboard/requests')
    d.wait_for_load_state('networkidle')
    link = d.locator('a[href^="/dashboard/requests/"]').first
    if link.count():
        d.goto(BASE + link.get_attribute('href'))
        d.wait_for_load_state('networkidle')
        check('request detail: email history section', d.get_by_role('heading', name='Email history').count() > 0)
        d.get_by_role('button', name='Check for replies').click()
        try:
            d.get_by_text('Reply checking is not set up yet').first.wait_for(timeout=6000)
            ok = True
        except Exception:
            ok = False
        check('reply check: honest "not set up" notice when IMAP is off', ok)
    else:
        check('request available', False)
    ctx.close()
    browser.close()
    check('no page errors', not errors, '; '.join(errors[:3]))

for name, ok, detail in results:
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))
print(f'\n{len(results) - len(failures)}/{len(results)} passed')
sys.exit(1 if failures else 0)