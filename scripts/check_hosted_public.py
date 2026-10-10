"""Read-only public checks of a deployed Concierge (no sign-in, no form submissions).

    python scripts/check_hosted_public.py https://your-app.up.railway.app
"""
import sys

from playwright.sync_api import sync_playwright

H = (sys.argv[1] if len(sys.argv) > 1 else 'https://web-production-41fc3c.up.railway.app').rstrip('/')
out = []


def chk(n, c, d=''):
    out.append(('PASS ' if c else 'FAIL ') + n + (f'  [{d}]' if d and not c else ''))


with sync_playwright() as p:
    b = p.chromium.launch()
    api = b.new_page()
    for path in ('/health', '/ready'):
        r = api.request.get(H + path)
        chk(f'{path} returns 200', r.status == 200, str(r.status))
    cfg = api.request.get(H + '/api/auth/config/').text()
    chk('auth config exposes no accounts or passwords', 'password' not in cfg.lower() and 'raleighdentistry' not in cfg)
    api.close()
    for w, h in [(1366, 900), (390, 844)]:
        pg = b.new_page(viewport={'width': w, 'height': h})
        errs = []
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(H + '/login', timeout=60000)
        pg.wait_for_load_state('networkidle', timeout=60000)
        html = pg.content()
        chk(f'{w}px: login form renders', pg.locator('#login-email').count() == 1)
        chk(f'{w}px: no "Demo environment" panel', 'Demo environment' not in html)
        chk(f'{w}px: no demo account emails', 'raleighdentistry.com' not in html)
        ov = pg.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
        chk(f'{w}px: no horizontal scroll', ov <= 1, f'{ov}px')
        chk(f'{w}px: no page errors', not errs, '; '.join(errs[:2]))
        if w == 1366:
            href = pg.get_by_text('Request access').first.get_attribute('href')
            chk('"Request access" opens the in-app onboarding form', bool(href) and href.startswith('/request-access'), str(href))
            chk('password visibility toggle present', pg.get_by_role('button', name='Show password').count() > 0)
            pg.goto(H + '/request-access')
            pg.wait_for_load_state('networkidle')
            chk('/request-access form renders', pg.get_by_role('button', name='Send request').count() == 1)
        pg.close()
    b.close()
print('\n'.join(out))
print(f"\n{sum(o.startswith('PASS') for o in out)}/{len(out)} passed")
sys.exit(0 if all(o.startswith('PASS') for o in out) else 1)