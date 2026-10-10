"""End-to-end check of appointment confirmation emails (LOCAL dev server on a throwaway DB copy).

Uses a real SMTP account and reads the delivered email back over IMAP, so only send to a
controlled inbox: the patient address is a plus-address of INBOX_USER.

    E2E_PASSWORD=...  INBOX_USER=you@gmail.com  INBOX_PASSWORD=<app password>  QA_SQLITE_PATH=...  \
        python scripts/e2e_confirmation.py
Never run against production.
"""
import email
import imaplib
import os
import re
import subprocess
import sys
import time
from datetime import date, timedelta

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = os.environ.get('E2E_BASE', 'http://127.0.0.1:8010')
BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend')
PY = sys.executable
OUT = os.environ.get('E2E_SHOTS', os.path.join(os.environ.get('TEMP', '.'), 'confirmation_shots'))
os.makedirs(OUT, exist_ok=True)
RUN = str(int(time.time()))[-6:]
INBOX_USER, INBOX_PW = os.environ['INBOX_USER'], os.environ['INBOX_PASSWORD'].replace(' ', '')
local, domain = INBOX_USER.split('@')
PATIENT = f'{local}+qa-confirm-{RUN}@{domain}'
results = []


def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail and not cond else ''), flush=True)


def django(code):
    env = dict(os.environ, SQLITE_PATH=os.environ['QA_SQLITE_PATH'], DJANGO_SETTINGS_MODULE='config.settings')
    out = subprocess.run([PY, '-c', 'import django;django.setup()\n' + code], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=120)
    if out.returncode:
        raise RuntimeError(out.stderr[-600:])
    return out.stdout.strip()


def fetch_email(subject_tag, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        box = imaplib.IMAP4_SSL('imap.gmail.com', 993)
        box.login(INBOX_USER, INBOX_PW)
        box.select('"[Gmail]/All Mail"', readonly=True)
        typ, data = box.search(None, 'X-GM-RAW', f'"{subject_tag}"')
        ids = data[0].split() if typ == 'OK' and data[0] else []
        if ids:
            typ, raw = box.fetch(ids[-1], '(BODY.PEEK[])')
            box.logout()
            msg = email.message_from_bytes(raw[0][1])
            html = text = ''
            for part in msg.walk():
                if part.get_content_type() == 'text/html':
                    html = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
                elif part.get_content_type() == 'text/plain':
                    text = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
            return msg, html, text
        box.logout()
        time.sleep(6)
    return None, '', ''


def login_desk(page):
    page.goto(f'{BASE}/login')
    page.get_by_label('Email').fill('desk@raleighdentistry.com')
    page.locator('#login-password').fill(os.environ['E2E_PASSWORD'])
    page.get_by_role('button', name='Sign in').click()
    page.wait_for_url('**/dashboard', timeout=15000)


overflow_js = 'document.documentElement.scrollWidth - document.documentElement.clientWidth'

appt_id = django(f"""
from apps.practices.models import Practice
from apps.appointments.models import Appointment
p = Practice.objects.get(slug='raleigh-dentistry')
a = Appointment.objects.create(practice=p, patient_name='Avery Synthetic', patient_email={PATIENT!r},
    intent='new_patient', service_name='New patient exam', preferred_date='Next week', preferred_time='Morning',
    message='Synthetic E2E request')
print(a.id)
""")
day1 = date.today() + timedelta(days=6)
day2 = date.today() + timedelta(days=8)

with sync_playwright() as p:
    browser = p.chromium.launch()
    errors = []
    ctx = browser.new_context(viewport={'width': 1366, 'height': 900})
    desk = ctx.new_page()
    desk.on('pageerror', lambda e: errors.append(str(e)))
    login_desk(desk)

    # Front desk: choose date + time, preview, send.
    desk.goto(f'{BASE}/dashboard/requests/{appt_id}')
    desk.wait_for_load_state('networkidle')
    desk.get_by_placeholder('Compose reply...').fill(f'Hello Avery,\n\nThank you for choosing us. ({RUN})')
    desk.locator('#offer-date').fill(day1.isoformat())
    desk.get_by_role('button', name='10:00 AM', exact=True).click()
    check('front desk: "Ask the patient to confirm" offered and on by default',
          desk.get_by_role('checkbox', name=re.compile('Ask the patient to confirm')).is_checked())
    body_val = desk.get_by_placeholder('Compose reply...').input_value()
    check('front desk: message updated with the chosen date and time',
          '10:00 AM' in body_val and 'buttons in this email' in body_val)
    desk.get_by_role('button', name='Preview email').click()
    frame = desk.frame_locator('iframe[title="Patient email preview"]')
    frame.get_by_text('Confirm appointment').wait_for(timeout=10000)
    check('front desk: preview shows the branded email', frame.get_by_text('Request a different time').count() > 0)
    desk.screenshot(path=os.path.join(OUT, 'desk_preview.png'))
    desk.get_by_role('button', name='Close').click()
    send_btn = desk.get_by_role('button', name='Send confirmation request')
    check('front desk: send button says what will happen', send_btn.count() == 1)
    send_btn.click()
    desk.get_by_text('Waiting for the patient').wait_for(timeout=30000)
    check('front desk: status card shows waiting for the patient', True)

    # The real delivered email.
    msg, html, text = fetch_email(f'{RUN}')
    check('email delivered to the controlled inbox (IMAP)', msg is not None)
    links = re.findall(r'href="([^"]+/appointment/[^"?]+)\?action=(confirm|reschedule)"', html)
    check('email contains confirm and reschedule links', {a for _, a in links} == {'confirm', 'reschedule'})
    check('plain-text version carries the link too', '/appointment/' in text)
    for w in (390, 760):
        ep = browser.new_page(viewport={'width': w, 'height': 1100})
        ep.set_content(html)
        ep.screenshot(path=os.path.join(OUT, f'email_{w}.png'), full_page=True)
        check(f'email {w}px: no horizontal overflow', ep.evaluate(overflow_js) <= 1)
        btn = ep.get_by_role('link', name='Confirm appointment').bounding_box()
        check(f'email {w}px: confirm button visible and tappable', btn is not None and btn['height'] >= 40 and btn['width'] >= 140)
        ep.close()
    confirm_link = [u for u, a in links if a == 'confirm'][0] + '?action=confirm'

    # Patient on a phone: opening the link changes nothing until they press Confirm.
    phone = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True).new_page()
    phone.on('pageerror', lambda e: errors.append(str(e)))
    phone.goto(confirm_link)
    phone.get_by_role('button', name='Confirm appointment').wait_for(timeout=15000)
    check('patient page: opening the link did not confirm anything',
          django(f"from apps.appointments.models import Appointment;print(Appointment.objects.get(id={appt_id!r}).status)") == 'contacted')
    phone.screenshot(path=os.path.join(OUT, 'patient_pending_390.png'), full_page=True)
    check('patient page 390px: no horizontal overflow', phone.evaluate(overflow_js) <= 1)
    phone.get_by_role('button', name='Confirm appointment').click()
    phone.get_by_role('heading', name="You're confirmed").wait_for(timeout=15000)
    phone.screenshot(path=os.path.join(OUT, 'patient_confirmed_390.png'), full_page=True)
    phone.reload()
    phone.get_by_role('heading', name="You're confirmed").wait_for(timeout=15000)
    check('patient page: confirmation persists on reload, no duplicate action offered',
          phone.get_by_role('button', name='Confirm appointment').count() == 0)

    desk.reload()
    desk.wait_for_load_state('networkidle')
    check('front desk: sees "Patient confirmed"', desk.get_by_text('Patient confirmed').count() > 0)
    status = django(f"from apps.appointments.models import Appointment;a=Appointment.objects.get(id={appt_id!r});print(a.status, bool(a.confirmed_at))")
    check('request status confirmed with timestamp', status == 'confirmed True', status)

    # New time replaces the old link; patient asks for a different time.
    desk.get_by_placeholder('Compose reply...').fill(f'Hello Avery, we have another time. ({RUN}b)')
    desk.locator('#offer-date').fill(day2.isoformat())
    desk.get_by_role('button', name='2:30 PM', exact=True).click()
    desk.get_by_role('button', name='Send confirmation request').click()
    desk.get_by_text('Waiting for the patient').wait_for(timeout=30000)
    phone.goto(confirm_link)
    phone.get_by_role('heading', name="This link can't be used").wait_for(timeout=15000)
    check('old link is rejected after a new time is sent', phone.get_by_text('replaced by a newer one').count() > 0)
    msg2, html2, _ = fetch_email(f'{RUN}b')
    link2 = re.findall(r'href="([^"]+/appointment/[^"?]+)\?action=reschedule"', html2)
    check('second email delivered with its own link', bool(link2) and link2[0] not in confirm_link)
    phone.goto(link2[0] + '?action=reschedule')
    phone.get_by_label(re.compile('Which days or times work better')).fill('Weekday mornings before 11')
    phone.get_by_role('button', name='Send request').click()
    phone.get_by_role('heading', name='Request sent').wait_for(timeout=15000)
    check('patient page: reschedule outcome stated honestly', phone.get_by_text('not confirmed').count() > 0)
    phone.screenshot(path=os.path.join(OUT, 'patient_reschedule_390.png'), full_page=True)
    desk.reload()
    desk.wait_for_load_state('networkidle')
    check('front desk: sees the reschedule request and note',
          desk.get_by_text('Patient asked for another time').count() > 0 and desk.get_by_text('Weekday mornings before 11').count() > 0)
    check('request back to pending for the front desk',
          django(f"from apps.appointments.models import Appointment;print(Appointment.objects.get(id={appt_id!r}).status)") == 'pending')

    phone.goto(f'{BASE}/appointment/this-is-not-a-real-token')
    phone.get_by_text('This link is not valid').wait_for(timeout=15000)
    check('invalid link shows a clear message', True)
    browser.close()
    check('no page errors', not errors, '; '.join(errors[:3]))

print(f"\nscreenshots: {OUT}")
print(f"{sum(ok for _, ok in results)}/{len(results)} passed")
sys.exit(0 if all(ok for _, ok in results) else 1)