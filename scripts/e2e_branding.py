"""Branding end-to-end check (LOCAL dev server on a throwaway DB copy only).

Env: PW (doctor), PWD2 (front desk) for the demo accounts on that copy, DKEY (demo practice widget key),
RKEY (another practice's key), QA_SERVER_LOG (server log path; console email backend prints emails there).
Never run against production.
"""
import tempfile
from PIL import Image, ImageDraw
import os, pathlib, re, time
from datetime import date, timedelta
from playwright.sync_api import sync_playwright
B = os.environ.get('E2E_BASE', 'http://127.0.0.1:8010'); T = tempfile.mkdtemp()
_logo = Image.new('RGBA', (900, 300), (0, 0, 0, 0)); ImageDraw.Draw(_logo).rounded_rectangle((10, 40, 260, 260), 40, fill=(18, 94, 74, 255)); _logo.save(T + '/qa_logo.png')
_ph = Image.new('RGB', (700, 900), (205, 180, 160)); ImageDraw.Draw(_ph).ellipse((200, 200, 500, 500), fill=(120, 90, 70)); _ph.save(T + '/qa_photo.jpg')
W = pathlib.Path(r'C:\Users\DIVYANSHU\Desktop\concierge_religh\widget\widget-test.html').as_uri()
res = []
def chk(n, c, d=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  [' + str(d) + ']') if d and not c else ''))
def login(pg, email, pw):
    pg.goto(B + '/login'); pg.get_by_label('Email').fill(email); pg.locator('#login-password').fill(pw)
    pg.get_by_role('button', name='Sign in').click(); pg.wait_for_url('**/dashboard', timeout=20000)
tag = str(int(time.time()))[-5:]
doc_name = 'Dr. Maya Chen ' + tag
with sync_playwright() as p:
    b = p.chromium.launch(); errs = []
    ctx = b.new_context(viewport={'width': 1366, 'height': 900}); pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
    login(pg, 'doctor@heyjarvis-demo.com', os.environ['PW'])
    pg.get_by_role('link', name='Branding & Widget', exact=True).click(); pg.wait_for_url('**/widget-settings'); pg.wait_for_load_state('networkidle')
    chk('Branding & Widget page shows the branding card', pg.get_by_role('heading', name='Practice branding').count() == 1)
    pg.locator('input[aria-label="Logo file"]').set_input_files(T + '/qa_logo.png')
    pg.get_by_alt_text('HeyJarvis Demo Dental logo').wait_for(timeout=15000)
    chk('logo uploads and previews', True)
    pg.locator('#brand-tagline').fill('Gentle family dentistry ' + tag)
    if pg.locator('#brand-instagram').count() == 0:
        pg.get_by_role('button', name=re.compile('Add website, reviews')).click()
    pg.locator('#brand-instagram').fill('instagram.com/heyjarvisdemo')
    pg.get_by_role('button', name='Save branding').click(); pg.wait_for_timeout(1500)
    pg.get_by_role('button', name='Add person').click()
    pg.get_by_label('New team member name').fill(doc_name); pg.get_by_label('New team member credentials').fill('DMD')
    pg.get_by_label('New team member bio').fill('Loves helping nervous patients feel at ease.')
    pg.get_by_role('button', name='Add', exact=True).click(); pg.get_by_text(doc_name).wait_for(timeout=10000)
    row = pg.locator('li', has_text=doc_name)
    row.locator('input[type=file]').set_input_files(T + '/qa_photo.jpg'); pg.wait_for_timeout(2500)
    pg.reload(); pg.wait_for_load_state('networkidle')
    chk('branding persists after refresh', pg.locator('#brand-tagline').input_value() == 'Gentle family dentistry ' + tag and pg.get_by_alt_text('HeyJarvis Demo Dental logo').count() == 1)
    chk('team member photo persists', pg.locator('li', has_text=doc_name).locator('img').count() == 1)
    pg.get_by_role('button', name='Preview patient email').click()
    fr = pg.frame_locator('iframe[title="Patient email preview"]'); fr.locator('img').first.wait_for(timeout=10000)
    chk('email preview carries logo, tagline and Instagram link', fr.get_by_text('Gentle family dentistry ' + tag).count() == 1 and fr.get_by_role('link', name='Instagram').count() == 1)
    pg.screenshot(path=T + r'\p7_email_preview.png'); pg.get_by_role('button', name='Close').click()
    pg.screenshot(path=T + r'\p7_branding_page.png')
    ctx.close()
    for vw in [(1366, 900), (390, 844)]:
        c2 = b.new_context(viewport={'width': vw[0], 'height': vw[1]}); w = c2.new_page(); w.on('pageerror', lambda e: errs.append(str(e)))
        w.goto(W + '?api=' + B + '&key=' + os.environ['DKEY']); w.locator('#heyjarvis-widget .launcher').click()
        w.locator('#heyjarvis-widget .chip').first.wait_for(timeout=30000); w.wait_for_timeout(800)
        chk(str(vw[0]) + 'px widget: logo in header', w.locator('#heyjarvis-widget .avatar.has-logo img').count() == 1)
        team = w.locator('#heyjarvis-widget .team')
        chk(str(vw[0]) + 'px widget: team strip with doctor', team.count() == 1 and doc_name in team.inner_text())
        ov = w.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth')
        chk(str(vw[0]) + 'px widget: no overflow', ov <= 1, ov)
        w.screenshot(path=T + '\\p7_widget_' + str(vw[0]) + '.png'); c2.close()
    c3 = b.new_context(); o = c3.new_page()
    o.goto(W + '?api=' + B + '&key=' + os.environ['RKEY']); o.locator('#heyjarvis-widget .launcher').click(); o.locator('#heyjarvis-widget .chip').first.wait_for(timeout=30000)
    chk('other practice widget unaffected (no logo, no team)', o.locator('#heyjarvis-widget .avatar.has-logo').count() == 0 and o.locator('#heyjarvis-widget .team').count() == 0)
    c3.close()
    c4 = b.new_context(viewport={'width': 1366, 'height': 900}); d = c4.new_page()
    login(d, 'frontdesk@heyjarvis-demo.com', os.environ['PWD2'])
    # Self-contained: create the request this check replies to (synthetic patient, console email only).
    import json, urllib.request
    def _post(path, body):
        req = urllib.request.Request(B + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Origin': B})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())
    _conv = _post('/api/v1/widget/conversation/', {'client_key': os.environ['DKEY'], 'session_id': 'brand-' + tag})
    _post('/api/v1/widget/submit/', {'client_key': os.environ['DKEY'], 'conversation_id': _conv['conversation_id'],
                                      'patient_name': 'Brand Check ' + tag, 'patient_email': 'brandcheck' + tag + '@example.com'})
    d.goto(B + '/dashboard/requests'); d.wait_for_load_state('networkidle')
    d.goto(B + d.locator('a[href^="/dashboard/requests/"]').first.get_attribute('href')); d.wait_for_load_state('networkidle')
    d.get_by_placeholder('Compose reply...').fill('Hello, we have a time for you (' + tag + ').')
    d.locator('#offer-date').fill((date.today() + timedelta(days=5)).isoformat()); d.get_by_role('button', name='10:00 AM', exact=True).click()
    d.get_by_role('button', name='Send confirmation request').click(); d.get_by_text('Waiting for the patient').wait_for(timeout=30000)
    c4.close(); time.sleep(1)
    log = open(os.environ['QA_SERVER_LOG'], encoding='utf-8', errors='replace').read()
    links = re.findall(r'(http://127\.0\.0\.1:8010/appointment/[A-Za-z0-9_-]+)', log)
    chk('confirmation email contains a patient link', bool(links))
    chk('confirmation email HTML carries the uploaded logo and links', '/api/v1/brand-assets/' in log and 'instagram.com/heyjarvisdemo' in log)
    if links:
        c5 = b.new_context(viewport={'width': 390, 'height': 844}); pp = c5.new_page()
        pp.goto(links[-1] + '?action=confirm'); pp.get_by_role('button', name='Confirm appointment').wait_for(timeout=15000)
        chk('patient page shows the practice logo', pp.get_by_alt_text('HeyJarvis Demo Dental').count() >= 1)
        pp.screenshot(path=T + r'\p7_patient_page.png', full_page=True); c5.close()
    c6 = b.new_context(); a = c6.new_page(); login(a, 'doctor@heyjarvis-demo.com', os.environ['PW'])
    a.goto(B + '/dashboard/widget-settings'); a.wait_for_load_state('networkidle')
    a.get_by_role('button', name='Remove', exact=True).click(); a.wait_for_timeout(1500)
    chk('logo removed -> initial shown instead', a.get_by_alt_text('HeyJarvis Demo Dental logo').count() == 0)
    c6.close(); b.close()
    chk('no page errors', not errs, '; '.join(errs[:2]))
print('\n' + str(sum(res)) + '/' + str(len(res)) + ' passed')