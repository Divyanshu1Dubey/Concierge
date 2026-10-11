"""
Recall, reactivation and review-request programs.

All three are off by default. A practice admin must switch them on and acknowledge the outreach notice
(review policies and patient-communication rules are the practice's responsibility). Even then nothing
is sent automatically: the scheduler drafts follow-up tasks and staff approve each message.

- Recall: patients whose next routine visit is due (treatment reminders). Opt-outs always respected.
- Reactivation: patients not seen for a long time. Only contacts marked as having agreed to outreach.
- Review requests: every patient with a completed visit is asked the same way (no screening of
  happy patients first, which Google's review policy forbids), at most once a year.
"""
import csv
import io
import re
from datetime import date, datetime, timedelta

from django.utils import timezone

from .consent import is_opted_out, normalize_phone
from .followups import ensure_task, first_name
from .models import FollowUpTask, GrowthSettings, RecallContact

MAX_IMPORT_ROWS = 5000
TRUE_WORDS = {'1', 'y', 'yes', 'true', 'consent', 'opted in', 'opt-in', 'x'}


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date(year, month, min(d.day, days[month - 1]))


def parse_date(value: str):
    value = (value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%d-%b-%Y', '%b %d, %Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Unrecognised date "{value[:20]}" (use YYYY-MM-DD or MM/DD/YYYY)')


def _norm_header(h: str) -> str:
    return re.sub(r'[^a-z]', '', (h or '').lower())


HEADER_ALIASES = {
    'name': {'name', 'patient', 'patientname', 'fullname'},
    'first_name': {'firstname', 'first', 'givenname'},
    'last_name': {'lastname', 'last', 'surname', 'familyname'},
    'email': {'email', 'emailaddress', 'patientemail'},
    'phone': {'phone', 'phonenumber', 'mobile', 'cell', 'cellphone', 'mobilephone'},
    'last_visit': {'lastvisit', 'lastvisitdate', 'lastappointment', 'lastseen', 'lasthygiene'},
    'next_due': {'nextdue', 'duedate', 'recalldue', 'nextvisit', 'recalldate'},
    'consent': {'consent', 'outreachconsent', 'marketingconsent', 'optin', 'okaytocontact'},
    'external_id': {'id', 'patientid', 'chartnumber', 'chart', 'externalid'},
}


def import_recall_csv(practice, text: str, interval_months: int) -> dict:
    """Create or update recall contacts from a CSV export. Existing contacts match on email, then phone."""
    reader = csv.reader(io.StringIO(text.lstrip('﻿')))
    try:
        headers = next(reader)
    except StopIteration:
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': ['The file is empty.']}
    columns = {}
    for idx, h in enumerate(headers):
        key = _norm_header(h)
        for field, aliases in HEADER_ALIASES.items():
            if key in aliases and field not in columns:
                columns[field] = idx
    if 'name' not in columns and 'first_name' not in columns:
        return {'created': 0, 'updated': 0, 'skipped': 0,
                'errors': ['Add a "name" column (or "first name" and "last name").']}
    if 'email' not in columns and 'phone' not in columns:
        return {'created': 0, 'updated': 0, 'skipped': 0, 'errors': ['Add an "email" or "phone" column.']}

    created = updated = skipped = 0
    errors = []

    def cell(row, field):
        idx = columns.get(field)
        return row[idx].strip() if idx is not None and idx < len(row) else ''

    for line_no, row in enumerate(reader, start=2):
        if line_no - 1 > MAX_IMPORT_ROWS:
            errors.append(f'Stopped after {MAX_IMPORT_ROWS} rows. Split the file to import more.')
            break
        if not any(c.strip() for c in row):
            continue
        name = cell(row, 'name') or ' '.join(t for t in (cell(row, 'first_name'), cell(row, 'last_name')) if t)
        email = cell(row, 'email').lower()[:254]
        raw_phone = cell(row, 'phone')
        phone = normalize_phone(raw_phone) if raw_phone else ''
        if email and ('@' not in email or '.' not in email.split('@')[-1]):
            errors.append(f'Row {line_no}: "{email[:40]}" is not a valid email.')
            email = ''
        if not name or not (email or phone):
            skipped += 1
            if len(errors) < 20:
                errors.append(f'Row {line_no}: needs a name and an email or phone number.')
            continue
        try:
            last_visit = parse_date(cell(row, 'last_visit'))
            next_due = parse_date(cell(row, 'next_due'))
        except ValueError as exc:
            skipped += 1
            if len(errors) < 20:
                errors.append(f'Row {line_no}: {exc}')
            continue
        if not next_due and last_visit:
            next_due = add_months(last_visit, interval_months)
        consent = cell(row, 'consent').lower() in TRUE_WORDS
        contact = None
        if email:
            contact = RecallContact.objects.filter(practice=practice, email__iexact=email).first()
        if contact is None and phone:
            contact = RecallContact.objects.filter(practice=practice, phone=phone).first()
        values = {'name': name[:200], 'email': email, 'phone': phone, 'last_visit': last_visit,
                  'next_due': next_due, 'consent_outreach': consent, 'external_id': cell(row, 'external_id')[:80]}
        if contact:
            for k, v in values.items():
                if v not in ('', None) or k == 'consent_outreach':
                    setattr(contact, k, v)
            contact.save()
            updated += 1
        else:
            RecallContact.objects.create(practice=practice, source='import', **values)
            created += 1
    return {'created': created, 'updated': updated, 'skipped': skipped, 'errors': errors[:20]}


def record_completed_visit(appointment):
    """A request marked completed keeps the patient on the recall list with the next due date."""
    practice = appointment.practice
    if not practice or not (appointment.patient_email or appointment.patient_phone):
        return None
    gs = GrowthSettings.for_practice(practice)
    today = timezone.localdate()
    email = (appointment.patient_email or '').lower()
    phone = normalize_phone(appointment.patient_phone) if appointment.patient_phone else ''
    contact = None
    if email:
        contact = RecallContact.objects.filter(practice=practice, email__iexact=email).first()
    if contact is None and phone:
        contact = RecallContact.objects.filter(practice=practice, phone=phone).first()
    if contact is None:
        contact = RecallContact(practice=practice, name=(appointment.patient_name or 'Patient')[:200],
                                email=email, phone=phone, source='heyjarvis')
    if contact.last_visit and contact.last_visit >= today:
        return contact
    contact.last_visit = today
    contact.next_due = add_months(today, gs.recall_interval_months)
    contact.status = 'active'
    contact.save()
    return contact


# ── Drafts ────────────────────────────────────────────────────────────────────────────────────

def draft_recall(contact, practice) -> tuple:
    name = first_name(contact.name)
    return (
        f"Time for your next visit at {practice.name}",
        f"Hi{(' ' + name) if name else ''},\n\n"
        f"Our records show you're due for your next routine visit at {practice.name}. "
        "Reply to this email with a few days and times that work for you and we'll find a spot.\n\n"
        + (f"You can also call us at {practice.phone}.\n\n" if practice.phone else '')
        + f"See you soon,\n{practice.name}",
    )


def draft_reactivation(contact, practice) -> tuple:
    name = first_name(contact.name)
    return (
        f"We'd love to see you again at {practice.name}",
        f"Hi{(' ' + name) if name else ''},\n\n"
        f"It's been a while since your last visit to {practice.name}. "
        "Regular check-ups help catch small problems early. If you'd like to book a visit, just reply with a few times that suit you.\n\n"
        + f"Best wishes,\n{practice.name}",
    )


def draft_review(appt, practice, review_link: str) -> tuple:
    name = first_name(appt.patient_name)
    return (
        f"How was your visit to {practice.name}?",
        f"Hi{(' ' + name) if name else ''},\n\n"
        f"Thank you for visiting {practice.name}. If you have a moment, we'd appreciate hearing about your experience:\n"
        f"{review_link}\n\n"
        "Your feedback helps other patients and helps our team improve.\n\n"
        f"Thank you,\n{practice.name}",
    )


# ── Scans ─────────────────────────────────────────────────────────────────────────────────────

def _outreach_allowed(gs) -> bool:
    return bool(gs.outreach_acknowledged_at)


def scan_outreach(practice, now=None) -> dict:
    now = now or timezone.now()
    today = timezone.localdate(now)
    gs = GrowthSettings.for_practice(practice)
    result = {'recall': 0, 'reactivation': 0, 'review': 0}
    if not _outreach_allowed(gs):
        return result

    if gs.recall_enabled:
        due = RecallContact.objects.filter(practice=practice, status='active', next_due__isnull=False,
                                           next_due__lte=today + timedelta(days=14))[:300]
        for c in due:
            if not _contactable(practice, c):
                continue
            subject, body = draft_recall(c, practice)
            _, made = ensure_task(
                practice, f"recall:{c.id}:{c.next_due.isoformat()}", kind=FollowUpTask.KIND_RECALL, recall_contact=c,
                patient_name=c.name, patient_email=c.email, patient_phone=c.phone,
                title=f"{c.name} is due for a recall visit",
                reason=f"Next visit due {c.next_due:%b %d, %Y}" + (f" (last seen {c.last_visit:%b %Y})." if c.last_visit else '.'),
                channel=_channel_for(practice, c), draft_subject=subject if _channel_for(practice, c) == 'email' else '',
                draft_body=body, draft_source='template', due_at=now,
            )
            result['recall'] += made

    if gs.reactivation_enabled:
        cutoff = add_months(today, -gs.reactivation_after_months)
        lapsed = RecallContact.objects.filter(practice=practice, status='active', consent_outreach=True,
                                              last_visit__isnull=False, last_visit__lte=cutoff)[:300]
        for c in lapsed:
            if not _contactable(practice, c):
                continue
            subject, body = draft_reactivation(c, practice)
            _, made = ensure_task(
                practice, f"reactivation:{c.id}:{c.last_visit.isoformat()}", kind=FollowUpTask.KIND_REACTIVATION,
                recall_contact=c, patient_name=c.name, patient_email=c.email, patient_phone=c.phone,
                title=f"{c.name} has not visited since {c.last_visit:%b %Y}",
                reason='Agreed to hear from the practice; not seen for over '
                       f'{gs.reactivation_after_months} months.',
                channel=_channel_for(practice, c), draft_subject=subject if _channel_for(practice, c) == 'email' else '',
                draft_body=body, draft_source='template', due_at=now,
            )
            result['reactivation'] += made

    if gs.review_requests_enabled and gs.review_link:
        from apps.appointments.models import Appointment
        recent = Appointment.objects.filter(practice=practice, status='completed',
                                            updated_at__gte=now - timedelta(days=7)).exclude(patient_email='')[:200]
        year_ago = now - timedelta(days=365)
        for appt in recent:
            email = appt.patient_email.lower()
            if is_opted_out(practice, 'email', email):
                continue
            if FollowUpTask.objects.filter(practice=practice, kind=FollowUpTask.KIND_REVIEW,
                                           patient_email__iexact=email, created_at__gte=year_ago).exists():
                continue
            subject, body = draft_review(appt, practice, gs.review_link)
            _, made = ensure_task(
                practice, f"review:{appt.id}", kind=FollowUpTask.KIND_REVIEW, appointment=appt,
                patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
                title=f"Ask {first_name(appt.patient_name) or 'the patient'} about their visit",
                reason='Visit marked completed. Every patient is asked the same way.',
                channel='email', draft_subject=subject, draft_body=body, draft_source='template', due_at=now,
            )
            result['review'] += made
    return result


def _contactable(practice, contact) -> bool:
    return bool(_channel_for(practice, contact))


def _channel_for(practice, contact) -> str:
    """Email when allowed, otherwise text; '' when the patient opted out of both."""
    if contact.email and not is_opted_out(practice, 'email', contact.email):
        return 'email'
    if contact.phone and not is_opted_out(practice, 'sms', contact.phone):
        return 'sms'
    return ''
