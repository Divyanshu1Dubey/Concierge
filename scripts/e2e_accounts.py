"""Browser checks for account lifecycle and data deletion against a LOCAL dev server.

Run the server with a throwaway database, console email and AI off, e.g.:
    DATABASE_URL=sqlite:///tmp/e2e.sqlite3 SMTP_USER= EMAIL_HOST_USER= AI_PROVIDER=none \\
        python manage.py runserver 127.0.0.1:8010
Then: python scripts/e2e_accounts.py
Never run against production.
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8010'
results, failures = [], []


def check(name, cond, detail=''):
    results.append((name, bool(cond), detail))
    if not cond:
        failures.append(name)


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
    errors = []

    # Forgot password: uniform confirmation, no account enumeration.
    page = browser.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(f'{BASE}/login')
    page.get_by_role('link', name='Forgot password?').click()
    page.wait_for_url('**/forgot-password')
    page.get_by_label('Email').fill('nobody-here@example.com')
    page.get_by_role('button', name='Send reset link').click()
    page.wait_for_timeout(800)
    check('forgot-password shows uniform confirmation', page.get_by_text("we've emailed a link").count() > 0)

    # Invalid reset link is rejected with a clear message.
    page.goto(f'{BASE}/reset-password?uid=MQ&token=bad-token&invite=1')
    check('invite page renders set-up heading', page.get_by_role('heading', name='Set up your account').count() > 0)
    page.get_by_label('New password').fill('Some-Strong-Passphrase-1')
    page.get_by_label('Confirm password').fill('Some-Strong-Passphrase-1')
    page.get_by_role('button', name='Create password').click()
    page.wait_for_timeout(800)
    check('invalid reset token rejected', page.get_by_text('invalid or has expired').count() > 0)
    page.close()

    # Practice admin: invite a staff member without a password -> invite email.
    ctx = browser.new_context()
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    login(page, 'Doctor (Practice Admin)')
    page.goto(f'{BASE}/dashboard/team')
    page.wait_for_load_state('networkidle')
    page.get_by_role('button', name='Add Team Member').click()
    email = f'invite-{int(time.time())}@example.com'
    page.get_by_placeholder('colleague@yourpractice.com').fill(email)
    page.get_by_role('button', name='Send Invite').click()
    page.wait_for_timeout(1500)
    check('team invite reports invite email sent', page.get_by_text(f'Invite email sent to {email}').count() > 0)
    check('invited member listed', page.get_by_text(email).count() > 0)

    # Profile modal exposes change password.
    page.get_by_role('button', name='Edit your profile').click()
    page.get_by_role('button', name='Change password').click()
    check('change-password form available', page.get_by_label('Current password').count() > 0)
    page.keyboard.press('Escape')
    page.goto(f'{BASE}/dashboard')

    # Practice admin deletes a patient request (with confirmation).
    page.goto(f'{BASE}/dashboard/requests')
    page.wait_for_load_state('networkidle')
    link = page.locator('a[href^="/dashboard/requests/"]').first
    if link.count():
        href = link.get_attribute('href')
        page.goto(BASE + href)
        page.wait_for_load_state('networkidle')
        page.get_by_role('button', name='Delete', exact=True).click()
        page.get_by_role('button', name='Delete permanently').click()
        page.wait_for_url('**/dashboard/requests', timeout=10000)
        page.wait_for_load_state('networkidle')
        check('request deleted and gone from inbox', page.locator(f'a[href="{href}"]').count() == 0)
    else:
        check('request available to delete', False, 'no requests in test DB')
    ctx.close()

    # Agency suspends a practice -> its staff are signed out / blocked.
    ctx = browser.new_context()
    desk = ctx.new_page()
    login(desk, 'Front Desk')
    actx = browser.new_context()
    agency = actx.new_page()
    login(agency, 'Agency Admin')
    token = agency.evaluate("localStorage.getItem('auth_token')")
    practices = agency.request.get(f'{BASE}/api/practices/all/', headers={'Authorization': f'Bearer {token}'}).json()['results']
    raleigh = next(p for p in practices if p['slug'] == 'raleigh-dentistry')
    agency.request.post(f"{BASE}/api/practices/{raleigh['id']}/toggle-status/", headers={'Authorization': f'Bearer {token}'})
    desk.goto(f'{BASE}/dashboard/requests')
    try:
        desk.wait_for_url('**/login?suspended=1', timeout=10000)
    except Exception:
        pass
    check('suspended practice staff redirected with message', 'suspended=1' in desk.url and desk.get_by_text('suspended').count() > 0, desk.url)
    # Re-activate so the environment is left as it was.
    agency.request.post(f"{BASE}/api/practices/{raleigh['id']}/toggle-status/", headers={'Authorization': f'Bearer {token}'})
    ctx.close()
    actx.close()
    browser.close()
    check('no page errors', not errors, '; '.join(errors[:3]))

for name, ok, detail in results:
    print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))
print(f'\n{len(results) - len(failures)}/{len(results)} passed')
sys.exit(1 if failures else 0)
