"""API for the follow-up queue, analytics, briefing, website check, recall, SMS and integrations."""
import hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.html import escape
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsPracticeAdmin, IsTenantMember, is_agency_user, is_practice_admin_user
from apps.practices.views import audit, practice_or_404

from . import analytics
from .models import (ContactPreference, FollowUpTask, GrowthSettings, Integration, JobRun, RecallContact,
                     SmsMessage, VisibilityReport)

logger = logging.getLogger(__name__)
STAFF = [permissions.IsAuthenticated, IsTenantMember]
ADMIN = [permissions.IsAuthenticated, IsPracticeAdmin]


def _bad(message, code=status.HTTP_400_BAD_REQUEST):
    return Response({'error': message, 'message': message}, status=code)


# ── Follow-up queue ───────────────────────────────────────────────────────────────────────────

def task_payload(t: FollowUpTask, now=None) -> dict:
    from .followups import priority
    return {
        'priority': priority(t, now),
        'id': str(t.id), 'kind': t.kind, 'kind_label': t.get_kind_display(), 'status': t.status,
        'title': t.title, 'reason': t.reason, 'channel': t.channel,
        'patient_name': t.patient_name, 'patient_email': t.patient_email, 'patient_phone': t.patient_phone,
        'appointment_id': str(t.appointment_id) if t.appointment_id else None,
        'recall_contact_id': t.recall_contact_id,
        'draft_subject': t.draft_subject, 'draft_body': t.draft_body, 'draft_source': t.draft_source,
        'due_at': t.due_at.isoformat(), 'snoozed_until': t.snoozed_until.isoformat() if t.snoozed_until else None,
        'created_at': t.created_at.isoformat(), 'completed_at': t.completed_at.isoformat() if t.completed_at else None,
        'completed_by': (t.completed_by.full_name or t.completed_by.email) if t.completed_by_id else '',
        'result_note': t.result_note, 'is_outreach': t.kind in FollowUpTask.OUTREACH_KINDS,
        'can_send': t.kind != FollowUpTask.KIND_RESCHEDULE and t.status in ('open', 'snoozed'),
        'is_public_reply': t.kind == FollowUpTask.KIND_REVIEW_REPLY,
    }


def refresh_queue(practice):
    """Keep the queue current even without the scheduler (cheap queries, at most once a minute)."""
    if not cache.add(f'growth-scan-{practice.id}', 1, 10):
        return
    from .followups import (scan_patient_replies, scan_reschedule_requests, scan_unconfirmed_offers,
                            scan_waiting_replies, wake_snoozed)
    now = timezone.now()
    gs = GrowthSettings.for_practice(practice)
    try:
        wake_snoozed(practice, now)
        scan_waiting_replies(practice, gs, now)
        scan_patient_replies(practice, gs, now)
        scan_unconfirmed_offers(practice, gs, now)
        scan_reschedule_requests(practice, now)
    except Exception as exc:
        logger.warning("Queue refresh failed for practice %s: %s", practice.id, type(exc).__name__)


class FollowUpListView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        refresh_queue(practice)
        qs = FollowUpTask.objects.filter(practice=practice).select_related('completed_by', 'appointment')
        state = request.query_params.get('status', 'open')
        if state == 'open':
            qs = qs.filter(status=FollowUpTask.STATUS_OPEN).order_by('due_at')
        elif state == 'snoozed':
            qs = qs.filter(status=FollowUpTask.STATUS_SNOOZED).order_by('snoozed_until')
        elif state == 'closed':
            qs = qs.filter(status__in=('done', 'sent', 'dismissed')).order_by('-completed_at')
        kind = request.query_params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)
        appt = request.query_params.get('appointment')
        if appt:
            qs = FollowUpTask.objects.filter(practice=practice, appointment_id=appt).order_by('-created_at')
        all_tasks = FollowUpTask.objects.filter(practice=practice)
        from .sms import sms_status
        gs = GrowthSettings.for_practice(practice)
        now = timezone.now()
        results = [task_payload(t, now) for t in qs[:200]]
        if state == 'open':
            # Most valuable contact first; ties keep the oldest first.
            results.sort(key=lambda r: (-r['priority']['score'], r['due_at']))
        return Response({
            'results': results,
            'counts': {
                'open': all_tasks.filter(status='open').count(),
                'snoozed': all_tasks.filter(status='snoozed').count(),
                'closed_7d': all_tasks.filter(status__in=('done', 'sent', 'dismissed'),
                                              completed_at__gte=timezone.now() - timedelta(days=7)).count(),
                'by_kind': {k: all_tasks.filter(status='open', kind=k).count() for k, _ in FollowUpTask.KIND_CHOICES},
            },
            'approval_policy': gs.approval_policy,
            'sms': sms_status(practice),
        })

    def post(self, request):
        """Staff add a manual follow-up for a request (e.g. 'call back Tuesday')."""
        practice, err = practice_or_404(request)
        if err:
            return err
        from apps.appointments.models import Appointment
        from .followups import ensure_task
        appt = get_object_or_404(Appointment, id=request.data.get('appointment_id'), practice=practice)
        title = str(request.data.get('title') or '').strip()[:200] or f"Follow up with {appt.patient_name or 'patient'}"
        try:
            hours = max(0, min(int(request.data.get('due_in_hours') or 0), 24 * 60))
        except (TypeError, ValueError):
            hours = 0
        task, _ = ensure_task(
            practice, f"manual:{appt.id}:{timezone.now().timestamp()}", kind=FollowUpTask.KIND_MANUAL, appointment=appt,
            patient_name=appt.patient_name, patient_email=appt.patient_email, patient_phone=appt.patient_phone,
            title=title, reason=str(request.data.get('note') or '')[:400],
            channel='email' if appt.patient_email else 'phone', due_at=timezone.now() + timedelta(hours=hours),
        )
        return Response(task_payload(task), status=status.HTTP_201_CREATED)


class FollowUpDetailView(APIView):
    permission_classes = STAFF

    def patch(self, request, task_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        task = get_object_or_404(FollowUpTask, id=task_id, practice=practice)
        action = request.data.get('action', 'edit')
        now = timezone.now()
        if action == 'edit':
            if 'draft_subject' in request.data:
                task.draft_subject = str(request.data['draft_subject'] or '')[:200]
            if 'draft_body' in request.data:
                task.draft_body = str(request.data['draft_body'] or '')[:5000]
                task.draft_source = 'staff'
            if request.data.get('channel') in ('email', 'sms', 'phone'):
                task.channel = request.data['channel']
        elif action == 'snooze':
            try:
                hours = max(1, min(int(request.data.get('hours') or 24), 24 * 30))
            except (TypeError, ValueError):
                hours = 24
            task.status, task.snoozed_until = FollowUpTask.STATUS_SNOOZED, now + timedelta(hours=hours)
        elif action in ('done', 'dismiss'):
            task.status = FollowUpTask.STATUS_DONE if action == 'done' else FollowUpTask.STATUS_DISMISSED
            task.completed_by, task.completed_at = request.user, now
            task.result_note = str(request.data.get('note') or ('Marked done' if action == 'done' else 'Dismissed'))[:300]
        elif action == 'reopen':
            task.status, task.completed_at, task.snoozed_until, task.due_at = FollowUpTask.STATUS_OPEN, None, None, now
        else:
            return _bad('Unknown action.')
        task.save()
        return Response(task_payload(task))


class FollowUpSendView(APIView):
    permission_classes = STAFF

    def post(self, request, task_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .followups import SendError, send_task_message
        task = get_object_or_404(FollowUpTask, id=task_id, practice=practice)
        subject = request.data.get('subject', task.draft_subject)
        body = request.data.get('body', task.draft_body)
        channel = request.data.get('channel', task.channel if task.channel != 'phone' else 'email')
        task.draft_subject, task.draft_body = str(subject or '')[:200], str(body or '')[:5000]
        try:
            result = send_task_message(task, request.user, task.draft_subject, task.draft_body, channel)
        except SendError as exc:
            return _bad(str(exc))
        audit(practice, request, 'follow_up_sent', {'task': str(task.id), 'kind': task.kind, 'channel': channel})
        task.refresh_from_db()
        return Response({'task': task_payload(task), **result,
                         'message': 'Sent. It now appears in the request history.' if task.appointment_id else 'Sent.'})


class FollowUpBatchSendView(APIView):
    """Send several reviewed drafts at once (only when the practice chose batch approval)."""
    permission_classes = STAFF

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        gs = GrowthSettings.for_practice(practice)
        if gs.approval_policy != GrowthSettings.APPROVAL_BATCH:
            return _bad('Batch sending is turned off. A practice admin can enable it in Growth settings.')
        ids = [str(i) for i in (request.data.get('ids') or [])][:50]
        from .followups import SendError, send_task_message
        sent, failed = 0, []
        for task in FollowUpTask.objects.filter(practice=practice, id__in=ids, status='open'):
            if task.kind == FollowUpTask.KIND_RESCHEDULE or task.channel == 'phone':
                failed.append({'id': str(task.id), 'error': 'Needs a person to handle.'})
                continue
            try:
                send_task_message(task, request.user, task.draft_subject, task.draft_body, task.channel)
                sent += 1
            except SendError as exc:
                failed.append({'id': str(task.id), 'error': str(exc)})
        audit(practice, request, 'follow_up_batch_sent', {'sent': sent, 'failed': len(failed)})
        return Response({'sent': sent, 'failed': failed})


class FollowUpAiDraftView(APIView):
    """Rewrite the current draft with AI (staff still review and send)."""
    permission_classes = STAFF

    def post(self, request, task_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        task = get_object_or_404(FollowUpTask, id=task_id, practice=practice)
        from apps.ai_service.engine import AIEngine
        engine = AIEngine()
        if not engine.available:
            return _bad('AI writing help is not available right now. You can edit the draft yourself.',
                        status.HTTP_503_SERVICE_UNAVAILABLE)
        context = ''
        if task.appointment_id:
            a = task.appointment
            context = (f"Request type: {a.service_name or a.intent}. Preferred: {a.preferred_date} {a.preferred_time}. "
                       f"Patient message: {(a.message or a.ai_summary or '')[:500]}")
        instruction = str(request.data.get('instruction') or 'Make it warm, clear and brief.')[:200]
        prompt = (f"Rewrite this email from a dental practice front desk to a patient. {instruction} "
                  "Keep any dates, times and links exactly. Do not invent prices, insurance coverage or availability. "
                  "Return only the email body.\n\nSituation: " + task.reason + "\n" + context +
                  "\n\nDraft:\n" + (request.data.get('body') or task.draft_body)[:3000])
        res = engine.chat(prompt, practice=practice, audience='staff')
        if not res.get('content'):
            return _bad('AI writing help did not respond. Try again or edit the draft yourself.',
                        status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'body': res['content'].strip()[:5000], 'source': 'ai'})


# ── Analytics & briefing ──────────────────────────────────────────────────────────────────────

class AnalyticsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        try:
            days = int(request.query_params.get('days', 30))
        except ValueError:
            days = 30
        days = days if days in (7, 30, 90) else 30
        data = analytics.overview(practice, days)
        if Integration.objects.filter(practice=practice, kind='nexhealth', status='connected').exists():
            data['unavailable'] = [u for u in data['unavailable'] if 'practice-management' not in u]
        return Response(data)


class BriefingView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .briefing import build, recipients
        from .models import BriefingLog
        payload = build(practice)
        history = [{'week_start': b.week_start.isoformat(), 'status': b.status, 'recipients': len(b.recipients or []),
                    'error': b.error} for b in BriefingLog.objects.filter(practice=practice)[:8]]
        return Response({'briefing': payload, 'recipients': recipients(practice), 'history': history})


class BriefingSendView(APIView):
    """Send this week's briefing now (practice admin). Still at most one per week."""
    permission_classes = ADMIN

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .briefing import send_briefing
        week = timezone.localdate()
        week = week - timedelta(days=week.weekday())
        result = send_briefing(practice, force_week=week)
        if result['status'] == 'sent':
            audit(practice, request, 'briefing_sent', {'recipients': result.get('recipients')})
            return Response({'status': 'sent', 'message': f"Briefing sent to {result['recipients']} recipient(s)."})
        if result.get('reason') == 'already sent':
            return _bad("This week's briefing was already sent.")
        if result.get('reason') == 'no recipients':
            return _bad('Add a briefing recipient first.')
        return _bad('The briefing could not be sent. Check email delivery settings.', status.HTTP_502_BAD_GATEWAY)


# ── Growth settings ───────────────────────────────────────────────────────────────────────────

def settings_payload(gs, practice):
    from .briefing import WEEKDAYS
    return {
        'waiting_alerts_enabled': gs.waiting_alerts_enabled, 'waiting_alert_hours': gs.waiting_alert_hours,
        'confirmation_nudges_enabled': gs.confirmation_nudges_enabled,
        'confirmation_nudge_hours': gs.confirmation_nudge_hours, 'approval_policy': gs.approval_policy,
        'briefing_enabled': gs.briefing_enabled, 'briefing_weekday': gs.briefing_weekday,
        'briefing_weekday_label': WEEKDAYS[gs.briefing_weekday % 7], 'briefing_hour': gs.briefing_hour,
        'briefing_recipients': gs.briefing_recipients or [],
        'recall_enabled': gs.recall_enabled, 'recall_interval_months': gs.recall_interval_months,
        'reactivation_enabled': gs.reactivation_enabled, 'reactivation_after_months': gs.reactivation_after_months,
        'review_requests_enabled': gs.review_requests_enabled, 'review_link': gs.review_link,
        'outreach_acknowledged': bool(gs.outreach_acknowledged_at),
        'outreach_acknowledged_at': gs.outreach_acknowledged_at.isoformat() if gs.outreach_acknowledged_at else None,
        'average_visit_value': float(gs.average_visit_value) if gs.average_visit_value is not None else None,
    }


class GrowthSettingsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        return Response(settings_payload(GrowthSettings.for_practice(practice), practice))

    def patch(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        if not is_practice_admin_user(request.user):
            return _bad('Only a practice admin can change these settings.', status.HTTP_403_FORBIDDEN)
        gs = GrowthSettings.for_practice(practice)
        d = request.data
        bools = ('waiting_alerts_enabled', 'confirmation_nudges_enabled', 'briefing_enabled', 'recall_enabled',
                 'reactivation_enabled', 'review_requests_enabled')
        ints = {'waiting_alert_hours': (1, 168), 'confirmation_nudge_hours': (2, 168), 'briefing_weekday': (0, 6),
                'briefing_hour': (0, 23), 'recall_interval_months': (1, 24), 'reactivation_after_months': (6, 60)}
        for k in bools:
            if k in d:
                setattr(gs, k, d[k] in (True, 'true', '1', 1))
        for k, (lo, hi) in ints.items():
            if k in d:
                try:
                    v = int(d[k])
                except (TypeError, ValueError):
                    return _bad(f'{k.replace("_", " ").capitalize()} must be a number.')
                if not lo <= v <= hi:
                    return _bad(f'{k.replace("_", " ").capitalize()} must be between {lo} and {hi}.')
                setattr(gs, k, v)
        if 'approval_policy' in d:
            if d['approval_policy'] not in dict(GrowthSettings.APPROVAL_CHOICES):
                return _bad('Unknown approval policy.')
            gs.approval_policy = d['approval_policy']
        if 'briefing_recipients' in d:
            raw = d['briefing_recipients'] or []
            if isinstance(raw, str):
                raw = [x for x in raw.replace(';', ',').split(',')]
            emails = []
            from django.core.validators import validate_email
            from django.core.exceptions import ValidationError
            for e in raw[:5]:
                e = str(e).strip()
                if not e:
                    continue
                try:
                    validate_email(e)
                except ValidationError:
                    return _bad(f'"{e[:60]}" is not a valid email address.')
                emails.append(e)
            gs.briefing_recipients = emails
        if 'review_link' in d:
            link = str(d['review_link'] or '').strip()
            if link and not link.startswith('https://'):
                return _bad('The review link must start with https://.')
            gs.review_link = link[:200]
        if 'average_visit_value' in d:
            v = d['average_visit_value']
            if v in ('', None):
                gs.average_visit_value = None
            else:
                try:
                    v = round(float(v), 2)
                except (TypeError, ValueError):
                    return _bad('Average visit value must be a number.')
                if not 0 <= v <= 100000:
                    return _bad('Average visit value looks wrong.')
                gs.average_visit_value = v
        if d.get('acknowledge_outreach') in (True, 'true', '1', 1):
            gs.outreach_acknowledged_by, gs.outreach_acknowledged_at = request.user, timezone.now()
        wants_outreach = gs.recall_enabled or gs.reactivation_enabled or gs.review_requests_enabled
        if wants_outreach and not gs.outreach_acknowledged_at:
            return _bad('Please read and accept the outreach notice before turning on recall, reactivation or review requests.')
        if gs.review_requests_enabled and not gs.review_link:
            return _bad('Add your Google review link before turning on review requests.')
        gs.save()
        audit(practice, request, 'growth_settings_updated', {k: d[k] for k in d if k != 'briefing_recipients'})
        return Response(settings_payload(gs, practice))


# ── Website visibility ────────────────────────────────────────────────────────────────────────

def report_payload(r: VisibilityReport, full=True) -> dict:
    out = {'id': str(r.id), 'url': r.url, 'status': r.status, 'error': r.error, 'score': r.score,
           'lighthouse': r.lighthouse, 'created_at': r.created_at.isoformat(), 'duration_ms': r.duration_ms}
    if full:
        out['findings'] = r.findings
        out['summary'] = {s: sum(1 for f in r.findings if f['status'] == s) for s in ('fail', 'warn', 'pass')}
    return out


class VisibilityView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .visibility import pagespeed_enabled
        reports = list(VisibilityReport.objects.filter(practice=practice)[:10])
        return Response({
            'website': practice.website,
            'latest': report_payload(reports[0]) if reports else None,
            'history': [report_payload(r, full=False) for r in reports],
            'pagespeed_enabled': pagespeed_enabled(),
        })


class VisibilityRunView(APIView):
    permission_classes = STAFF

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        url = str(request.data.get('url') or practice.website or '').strip()
        if not url:
            return _bad('Add your website address first (Practice Settings) or enter it here.')
        if not cache.add(f'visibility-run-{practice.id}', 1, 20):
            return _bad('A check just ran. Wait a few seconds and try again.', status.HTTP_429_TOO_MANY_REQUESTS)
        from .visibility import run_check
        report = run_check(practice, url, user=request.user)
        audit(practice, request, 'visibility_check', {'url': report.url, 'status': report.status, 'score': report.score})
        code = status.HTTP_201_CREATED if report.status == 'ok' else status.HTTP_200_OK
        return Response(report_payload(report), status=code)


class VisibilityDetailView(APIView):
    permission_classes = STAFF

    def get(self, request, report_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        return Response(report_payload(get_object_or_404(VisibilityReport, id=report_id, practice=practice)))


class FactsExportView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .visibility import facts_export
        return Response(facts_export(practice, request))


# ── Knowledge suggestions ─────────────────────────────────────────────────────────────────────

class KnowledgeSuggestView(APIView):
    """Suggest an answer to an unanswered patient question from the practice's existing facts only."""
    permission_classes = ADMIN

    def post(self, request, question_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        from apps.practices.models import UnansweredQuestion
        q = get_object_or_404(UnansweredQuestion, id=question_id, practice=practice)
        lower = q.question.lower()
        if any(w in lower for w in ('price', 'cost', 'how much', 'insurance cover', 'covered', 'fee')):
            return Response({'suggestion': '', 'reason': 'Prices and insurance coverage must come from your team, so no draft was written.'})
        from apps.ai_service.engine import AIEngine, build_practice_facts
        engine = AIEngine()
        if not engine.available:
            return Response({'suggestion': '', 'reason': 'AI suggestions are not available right now. Write the answer yourself.'})
        prompt = ("Using ONLY the practice facts below, draft a short answer (2-3 sentences) a dental front desk could "
                  "approve for this patient question. If the facts do not contain the answer, reply exactly NO_ANSWER. "
                  "Never invent prices, insurance coverage, availability or medical advice.\n\nFacts:\n"
                  + build_practice_facts(practice)[:6000] + "\n\nQuestion: " + q.question)
        res = engine.chat(prompt, practice=practice, audience='staff')
        text = (res.get('content') or '').strip()
        if not text or 'NO_ANSWER' in text:
            return Response({'suggestion': '', 'reason': 'Your saved facts do not answer this yet. Write the answer yourself.'})
        return Response({'suggestion': text[:1500], 'reason': 'Suggested from your saved facts. Review before saving; it is not shown to patients until you save it.'})


# ── Recall list ───────────────────────────────────────────────────────────────────────────────

def contact_payload(c: RecallContact, practice) -> dict:
    from .consent import is_opted_out
    return {'id': c.id, 'name': c.name, 'email': c.email, 'phone': c.phone,
            'last_visit': c.last_visit.isoformat() if c.last_visit else None,
            'next_due': c.next_due.isoformat() if c.next_due else None, 'status': c.status,
            'consent_outreach': c.consent_outreach, 'source': c.source, 'notes': c.notes,
            'opted_out_email': bool(c.email) and is_opted_out(practice, 'email', c.email),
            'opted_out_sms': bool(c.phone) and is_opted_out(practice, 'sms', c.phone)}


class RecallListView(APIView):
    permission_classes = STAFF
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        qs = RecallContact.objects.filter(practice=practice)
        q = (request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
        due = request.query_params.get('due')
        today = timezone.localdate()
        if due == 'overdue':
            qs = qs.filter(next_due__lt=today, status='active')
        elif due == 'soon':
            qs = qs.filter(next_due__gte=today, next_due__lte=today + timedelta(days=30), status='active')
        total = RecallContact.objects.filter(practice=practice)
        return Response({
            'results': [contact_payload(c, practice) for c in qs[:300]],
            'counts': {'total': total.count(), 'overdue': total.filter(next_due__lt=today, status='active').count(),
                       'due_soon': total.filter(next_due__gte=today, next_due__lte=today + timedelta(days=30), status='active').count()},
        })

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .consent import normalize_phone
        from .outreach import add_months, parse_date
        name = str(request.data.get('name') or '').strip()[:200]
        email = str(request.data.get('email') or '').strip().lower()[:254]
        phone = normalize_phone(str(request.data.get('phone') or '')) if request.data.get('phone') else ''
        if not name or not (email or phone):
            return _bad('Add a name and an email or phone number.')
        if request.data.get('phone') and not phone:
            return _bad('That phone number does not look valid.')
        try:
            last_visit = parse_date(str(request.data.get('last_visit') or ''))
            next_due = parse_date(str(request.data.get('next_due') or ''))
        except ValueError as exc:
            return _bad(str(exc))
        gs = GrowthSettings.for_practice(practice)
        if not next_due and last_visit:
            next_due = add_months(last_visit, gs.recall_interval_months)
        if email and RecallContact.objects.filter(practice=practice, email__iexact=email).exists():
            return _bad('A patient with this email is already on the list.')
        c = RecallContact.objects.create(practice=practice, name=name, email=email, phone=phone, last_visit=last_visit,
                                         next_due=next_due, source='staff',
                                         consent_outreach=request.data.get('consent_outreach') in (True, 'true', '1', 1))
        return Response(contact_payload(c, practice), status=status.HTTP_201_CREATED)


class RecallImportView(APIView):
    permission_classes = ADMIN
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        f = request.FILES.get('file')
        if not f:
            return _bad('Choose a CSV file to import.')
        if f.size > 3 * 1024 * 1024:
            return _bad('The file is larger than 3 MB. Split it into smaller files.')
        raw = f.read()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('latin-1')
        from .outreach import import_recall_csv
        result = import_recall_csv(practice, text, GrowthSettings.for_practice(practice).recall_interval_months)
        audit(practice, request, 'recall_import', {k: result[k] for k in ('created', 'updated', 'skipped')})
        return Response(result)


class RecallDetailView(APIView):
    permission_classes = STAFF

    def patch(self, request, contact_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        c = get_object_or_404(RecallContact, id=contact_id, practice=practice)
        from .outreach import parse_date
        try:
            for k in ('last_visit', 'next_due'):
                if k in request.data:
                    setattr(c, k, parse_date(str(request.data[k] or '')))
        except ValueError as exc:
            return _bad(str(exc))
        if request.data.get('status') in ('active', 'scheduled', 'inactive'):
            c.status = request.data['status']
        if 'consent_outreach' in request.data:
            c.consent_outreach = request.data['consent_outreach'] in (True, 'true', '1', 1)
        if 'notes' in request.data:
            c.notes = str(request.data['notes'] or '')[:300]
        c.save()
        return Response(contact_payload(c, practice))

    def delete(self, request, contact_id):
        practice, err = practice_or_404(request)
        if err:
            return err
        if not is_practice_admin_user(request.user):
            return _bad('Only a practice admin can remove patients from the list.', status.HTTP_403_FORBIDDEN)
        get_object_or_404(RecallContact, id=contact_id, practice=practice).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactPreferenceView(APIView):
    """List opt-outs, or record an opt-out / opt-in on a patient's behalf."""
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        prefs = ContactPreference.objects.filter(practice=practice, opted_out=True).order_by('-updated_at')[:300]
        return Response({'results': [{'channel': p.channel, 'address': p.address, 'source': p.source,
                                      'opted_out_at': p.opted_out_at.isoformat() if p.opted_out_at else None} for p in prefs]})

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .consent import set_opt_out
        channel = request.data.get('channel')
        if channel not in ('email', 'sms'):
            return _bad('Choose email or text message.')
        pref = set_opt_out(practice, channel, str(request.data.get('address') or ''),
                           request.data.get('opted_out', True) in (True, 'true', '1', 1), source='staff')
        if pref is None:
            return _bad('Enter a valid email address or phone number.')
        audit(practice, request, 'contact_preference_changed', {'channel': channel, 'opted_out': pref.opted_out})
        return Response({'channel': pref.channel, 'address': pref.address, 'opted_out': pref.opted_out})


# ── SMS ───────────────────────────────────────────────────────────────────────────────────────

def sms_payload(m: SmsMessage) -> dict:
    return {'id': str(m.id), 'direction': m.direction, 'to': m.to_number, 'from': m.from_number, 'body': m.body,
            'status': m.status, 'error': m.error, 'created_at': m.created_at.isoformat(),
            'sent_by': (m.sent_by.full_name or m.sent_by.email) if m.sent_by_id else ''}


class SmsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .sms import sms_status
        qs = SmsMessage.objects.filter(practice=practice).select_related('sent_by')
        appt = request.query_params.get('appointment')
        if appt:
            qs = qs.filter(appointment_id=appt)
        return Response({'status': sms_status(practice), 'results': [sms_payload(m) for m in qs[:100]]})

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from apps.appointments.models import Appointment
        from .sms import SmsError, send_sms
        appt = None
        if request.data.get('appointment_id'):
            appt = get_object_or_404(Appointment, id=request.data['appointment_id'], practice=practice)
        to = str(request.data.get('to') or (appt.patient_phone if appt else '') or '')
        try:
            msg = send_sms(practice, to, str(request.data.get('body') or ''), user=request.user, appointment=appt)
        except SmsError as exc:
            return _bad(str(exc))
        audit(practice, request, 'sms_sent', {'appointment': str(appt.id) if appt else None})
        return Response(sms_payload(msg), status=status.HTTP_201_CREATED)


def _twilio_params(request):
    return {k: request.POST.get(k) for k in request.POST.keys()}


class SmsInboundView(APIView):
    """Twilio inbound-message webhook. Requests must carry a valid X-Twilio-Signature."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    parser_classes = [FormParser, MultiPartParser]

    def post(self, request):
        from .sms import find_practice_for_number, handle_inbound, valid_twilio_signature
        params = _twilio_params(request)
        practice, cfg = find_practice_for_number(params.get('To', ''))
        token = (cfg or {}).get('auth_token', '')
        url = request.build_absolute_uri()
        public = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
        if public:
            url = public + request.get_full_path()
        if not valid_twilio_signature(token, url, params, request.headers.get('X-Twilio-Signature', '')):
            return HttpResponse(status=403)
        handle_inbound(params, practice_hint=practice)
        return HttpResponse('<?xml version="1.0" encoding="UTF-8"?><Response></Response>', content_type='text/xml')


class SmsStatusView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    parser_classes = [FormParser, MultiPartParser]

    def post(self, request):
        from .sms import signing_token, valid_twilio_signature
        params = _twilio_params(request)
        msg = SmsMessage.objects.filter(provider_id=params.get('MessageSid', ''), direction='out').select_related('practice').first() \
            if params.get('MessageSid') else None
        if not msg:
            return HttpResponse(status=204)
        cfg = {'auth_token': signing_token(msg.practice)}
        public = (getattr(settings, 'APP_PUBLIC_URL', '') or '').rstrip('/')
        url = (public + request.get_full_path()) if public else request.build_absolute_uri()
        if not valid_twilio_signature(cfg.get('auth_token', ''), url, params, request.headers.get('X-Twilio-Signature', '')):
            return HttpResponse(status=403)
        state = params.get('MessageStatus', '')
        if state in ('delivered', 'undelivered', 'failed', 'sent'):
            msg.status = 'delivered' if state == 'delivered' else ('failed' if state in ('undelivered', 'failed') else 'sent')
            if msg.status == 'failed':
                msg.error = f"Carrier did not deliver the message (code {params.get('ErrorCode', 'unknown')})."[:300]
            msg.save(update_fields=['status', 'error'])
        return HttpResponse(status=204)


# ── Unsubscribe (public) ──────────────────────────────────────────────────────────────────────

def _simple_page(title, body, form=None):
    form_html = ''
    if form:
        form_html = (f'<form method="post"><button type="submit" style="background:#0d9488;color:#fff;border:0;'
                     f'padding:12px 20px;border-radius:10px;font:600 15px system-ui;cursor:pointer">{escape(form)}</button></form>')
    html = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{escape(title)}</title></head><body style="margin:0;background:#f4f2ec;font:16px/1.6 system-ui,sans-serif;color:#1c2b24">'
            f'<main style="max-width:480px;margin:64px auto;padding:28px;background:#fff;border-radius:16px;border:1px solid #e7e3d9">'
            f'<h1 style="font:600 22px Georgia,serif;margin:0 0 12px">{escape(title)}</h1><p>{escape(body)}</p>{form_html}</main></body></html>')
    return HttpResponse(html)


class UnsubscribeView(APIView):
    """GET shows a confirmation button (so link scanners cannot opt people out); POST records the opt-out."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def _resolve(self, token):
        from apps.practices.models import Practice
        from .consent import read_unsubscribe_token
        data = read_unsubscribe_token(token)
        if not data:
            return None, None
        return Practice.objects.filter(id=data[0]).first(), data[1]

    def get(self, request, token):
        practice, email = self._resolve(token)
        if not practice:
            return _simple_page('Link not recognised', 'This unsubscribe link is not valid. Please contact the practice directly.')
        return _simple_page(f'Stop emails from {practice.name}?',
                            f'We will stop sending reminders and updates to {email}. Messages about a request you make yourself may still be sent.',
                            form='Unsubscribe')

    def post(self, request, token):
        practice, email = self._resolve(token)
        if not practice:
            return _simple_page('Link not recognised', 'This unsubscribe link is not valid. Please contact the practice directly.')
        from .consent import set_opt_out
        set_opt_out(practice, 'email', email, True, source='unsubscribe_link')
        return _simple_page('You are unsubscribed', f'{practice.name} will no longer send reminders or updates to {email}.')


# ── Integrations overview & connections ───────────────────────────────────────────────────────

def integration_overview(practice) -> list:
    from apps.emails.inbound import inbound_mailbox_configured
    from .integrations import gbp_app_configured
    from .jobs import scheduler_status
    from .sms import sms_status
    from .visibility import pagespeed_enabled
    integ = {i.kind: i for i in Integration.objects.filter(practice=practice)}

    def row(key, name, state, detail, action=None, category='core', requirements=None, extra=None):
        out = {'key': key, 'name': name, 'state': state, 'detail': detail, 'action': action, 'category': category,
               'requirements': requirements or []}
        if extra:
            out.update(extra)
        return out

    provider = practice.email_providers.filter(is_active=True).first()
    custom = bool(provider and provider.provider_type == 'smtp' and provider.smtp_host)
    email_ok = (provider.last_test_status == 'SUCCESS') if custom else bool(getattr(settings, 'EMAIL_CONFIGURED', False))
    backend = getattr(settings, 'EMAIL_BACKEND', '')
    rows = [row('email', 'Email sending', 'working' if email_ok else 'needs_setup',
                ('Your own mail server passed its last test.' if custom else
                 ('Platform email via Resend (HTTPS).' if 'Resend' in backend else 'Platform email is configured.'))
                if email_ok else 'Email is not configured, so replies cannot be sent.',
                '/dashboard/email-settings')]
    rows.append(row('replies', 'Patient email replies', 'working' if inbound_mailbox_configured() else 'needs_setup',
                    'Replies are collected and attached to each request.' if inbound_mailbox_configured()
                    else 'Reply collection is off (IMAP_HOST / IMAP_USER / IMAP_PASSWORD on the server).',
                    requirements=['A mailbox the platform can read over IMAP']))
    sched = scheduler_status()
    rows.append(row('scheduler', 'Scheduled jobs', 'working' if sched['healthy'] else 'needs_setup',
                    (f"Last run {sched['last_run'][:16].replace('T', ' ')} UTC." if sched['last_run'] else 'Has never run.')
                    + ('' if sched['healthy'] else ' Alerts, briefings and overnight reply collection need a cron service calling the job endpoint.'),
                    requirements=['CRON_SECRET on the server', 'A cron service calling /api/v1/growth/cron/run/ every 10 minutes']))
    s = sms_status(practice)
    rows.append(row('sms', 'Text messaging (Twilio)', 'test_mode' if s['mode'] == 'console' else ('working' if s['configured'] else 'not_connected'),
                    s['detail'], category='channels',
                    requirements=['Twilio account and phone number (paid per message)', 'A2P 10DLC registration for US texting',
                                  'Patient consent to receive texts'],
                    extra={'connected_source': (integ.get('twilio').config or {}).get('from_number', '') if integ.get('twilio') else ''}))
    g = integ.get('google_business')
    g_state = g.status if g else 'not_connected'
    rows.append(row('google_business', 'Google Business Profile',
                    'working' if g_state == 'connected' else ('error' if g_state == 'error' else
                                                              ('awaiting_approval' if not gbp_app_configured() else 'not_connected')),
                    (g.last_error if g and g.last_error else
                     (f"Connected{(' to ' + g.config.get('title')) if g and (g.config or {}).get('title') else ''}." if g_state == 'connected'
                      else ('Waiting for Google to approve API access for this HeyJarvis server.' if not gbp_app_configured()
                            else 'Connect to read reviews, draft replies and check profile consistency.'))),
                    category='visibility',
                    requirements=['Google approval of Business Profile API access (application form, about 14 days)',
                                  'GOOGLE_BUSINESS_CLIENT_ID and GOOGLE_BUSINESS_CLIENT_SECRET on the server',
                                  'Owner or manager access to the practice profile'],
                    extra={'location': (g.config or {}).get('title', '') if g else '', 'app_configured': gbp_app_configured()}))
    rows.append(row('pagespeed', 'Google PageSpeed (Lighthouse)', 'working' if pagespeed_enabled() else 'not_connected',
                    'Website checks include Lighthouse scores.' if pagespeed_enabled()
                    else 'Website checks run without Lighthouse scores. Add a free PAGESPEED_API_KEY to include them.',
                    category='visibility', requirements=['Free Google Cloud API key (PAGESPEED_API_KEY)']))
    n = integ.get('nexhealth')
    n_state = n.status if n else 'not_connected'
    rows.append(row('nexhealth', 'Practice management (NexHealth)',
                    {'connected': 'working', 'error': 'error', 'pending': 'needs_setup'}.get(n_state, 'not_connected'),
                    (n.last_error if n and n.last_error else
                     ('Connected: availability can be read from your practice software.' if n_state == 'connected'
                      else ('Saved. Run "Test connection" to finish.' if n_state == 'pending'
                            else 'Connect to read real availability from Dentrix, Open Dental, Eaglesoft and others.'))),
                    category='operations',
                    requirements=['NexHealth Synchronizer API key (usage-based pricing)', 'Business Associate Agreement with NexHealth',
                                  'Practice subdomain and location ID'],
                    extra={'subdomain': (n.config or {}).get('subdomain', '') if n else '',
                           'location_id': (n.config or {}).get('location_id', '') if n else ''}))
    rows.append(row('wordpress', 'WordPress plugin', 'available', 'Download the plugin to install the chat on WordPress sites.',
                    '/dashboard/installation', category='website'))
    return rows


class IntegrationsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        return Response({'integrations': integration_overview(practice)})


class GoogleConnectView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .integrations import IntegrationError, gbp_authorize_url
        try:
            return Response({'url': gbp_authorize_url(practice, request.user)})
        except IntegrationError as exc:
            return _bad(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)


class GoogleCallbackView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        from apps.practices.models import Practice
        from apps.users.models import User
        from .followups import dashboard_link
        from .integrations import IntegrationError, gbp_exchange_code, gbp_read_state
        back = dashboard_link('/dashboard/integrations')
        state = gbp_read_state(request.query_params.get('state', ''))
        if not state or request.query_params.get('error'):
            return HttpResponseRedirect(back + '?google=cancelled')
        practice = Practice.objects.filter(id=state['p']).first()
        user = User.objects.filter(id=state['u'], is_active=True).first()
        if not practice or not user:
            return HttpResponseRedirect(back + '?google=failed')
        try:
            gbp_exchange_code(practice, user, request.query_params.get('code', ''))
        except IntegrationError:
            return HttpResponseRedirect(back + '?google=failed')
        return HttpResponseRedirect(back + '?google=connected')


def _gbp(request, fn, *args, admin=False):
    practice, err = practice_or_404(request)
    if err:
        return None, err
    if admin and not is_practice_admin_user(request.user):
        return None, _bad('Only a practice admin can do this.', status.HTTP_403_FORBIDDEN)
    from .integrations import IntegrationError
    try:
        return fn(practice, *args), None
    except IntegrationError as exc:
        return None, _bad(str(exc), status.HTTP_502_BAD_GATEWAY)


class GoogleLocationsView(APIView):
    permission_classes = ADMIN

    def get(self, request):
        from .integrations import gbp_locations
        data, err = _gbp(request, gbp_locations)
        return err or Response({'locations': data})

    def post(self, request):
        from .integrations import gbp_select_location
        d = request.data
        data, err = _gbp(request, gbp_select_location, str(d.get('account', '')), str(d.get('location', '')), str(d.get('title', '')))
        return err or Response({'status': 'saved'})


class GoogleReviewsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        from .integrations import gbp_reviews
        data, err = _gbp(request, gbp_reviews, request.query_params.get('page_token', ''))
        return err or Response(data)


class GoogleReviewDraftView(APIView):
    permission_classes = STAFF

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        from .integrations import draft_review_reply
        review = {'reviewer': str(request.data.get('reviewer', ''))[:80], 'comment': str(request.data.get('comment', ''))[:2000]}
        try:
            review['rating'] = int(request.data.get('rating') or 0)
        except (TypeError, ValueError):
            review['rating'] = 0
        return Response({'draft': draft_review_reply(practice, review)})


class GoogleReviewReplyView(APIView):
    permission_classes = STAFF

    def post(self, request):
        from .integrations import gbp_reply
        data, err = _gbp(request, gbp_reply, str(request.data.get('review', '')), str(request.data.get('comment', '')))
        if err:
            return err
        practice, _ = practice_or_404(request)
        audit(practice, request, 'google_review_reply', {'review': str(request.data.get('review', ''))[-40:]})
        return Response({'status': 'posted', 'message': 'Reply published on Google.'})


class GooglePostView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import gbp_post
        data, err = _gbp(request, gbp_post, str(request.data.get('summary', '')), str(request.data.get('cta_url', '')))
        if err:
            return err
        practice, _ = practice_or_404(request)
        audit(practice, request, 'google_post_published', {})
        return Response({'status': 'posted', 'message': 'Update published to your Google Business Profile.'})


class GoogleDisconnectView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import gbp_disconnect
        _, err = _gbp(request, gbp_disconnect)
        if err:
            return err
        practice, _ = practice_or_404(request)
        audit(practice, request, 'google_disconnected', {})
        return Response({'status': 'disconnected'})


class NexHealthView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import nex_save
        d = request.data
        _, err = _gbp(request, nex_save, request.user, str(d.get('api_key', '')), str(d.get('subdomain', '')),
                      str(d.get('location_id', '')))
        if err:
            return err
        practice, _ = practice_or_404(request)
        audit(practice, request, 'nexhealth_saved', {})
        return Response({'status': 'saved', 'message': 'Saved. Run "Test connection" to finish.'})


class NexHealthTestView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import nex_test
        data, err = _gbp(request, nex_test)
        return err or Response({'status': 'connected', **data})


class NexHealthSlotsView(APIView):
    permission_classes = STAFF

    def get(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        if not Integration.objects.filter(practice=practice, kind='nexhealth', status='connected').exists():
            return Response({'connected': False, 'slots': []})
        from .integrations import nex_slots
        start = request.query_params.get('start_date') or timezone.localdate().isoformat()
        data, err = _gbp(request, nex_slots, start, request.query_params.get('days', 7))
        return err or Response({'connected': True, **data})


class NexHealthDisconnectView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import nex_disconnect
        _, err = _gbp(request, nex_disconnect)
        return err or Response({'status': 'disconnected'})


class TwilioView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import twilio_save
        d = request.data
        _, err = _gbp(request, twilio_save, request.user, str(d.get('account_sid', '')), str(d.get('auth_token', '')),
                      str(d.get('from_number', '')))
        if err:
            return err
        practice, _ = practice_or_404(request)
        audit(practice, request, 'twilio_connected', {})
        return Response({'status': 'connected'})


class TwilioDisconnectView(APIView):
    permission_classes = ADMIN

    def post(self, request):
        from .integrations import twilio_disconnect
        _, err = _gbp(request, twilio_disconnect)
        return err or Response({'status': 'disconnected'})


# ── Scheduler ─────────────────────────────────────────────────────────────────────────────────

def _is_cron(request) -> bool:
    secret = getattr(settings, 'CRON_SECRET', '')
    return bool(secret) and hmac.compare_digest(request.headers.get('X-Cron-Secret', ''), secret)


class CronRunView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        if not _is_cron(request):
            return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        from .jobs import JOBS, run_due_jobs
        only = [j for j in (request.data.get('jobs') or []) if j in JOBS] if isinstance(request.data, dict) else None
        return Response({'ran': run_due_jobs(only=only or None)})


class CronStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_agency_user(request.user):
            return _bad('Only agency admins can view the scheduler.', status.HTTP_403_FORBIDDEN)
        from .jobs import scheduler_status
        recent = [{'job': r.job, 'status': r.status, 'started_at': r.started_at.isoformat(), 'error': r.error,
                   'result': r.result} for r in JobRun.objects.all()[:30]]
        return Response({**scheduler_status(), 'recent': recent})

    def post(self, request):
        """Agency admin: run jobs now (each still runs once per window unless forced)."""
        if not is_agency_user(request.user):
            return _bad('Only agency admins can run jobs.', status.HTTP_403_FORBIDDEN)
        from .jobs import JOBS, run_due_jobs
        only = [j for j in (request.data.get('jobs') or []) if j in JOBS] or None
        return Response({'ran': run_due_jobs(only=only, force=bool(request.data.get('force')))})


# ── System status (agency) ────────────────────────────────────────────────────────────────────

class SystemStatusView(APIView):
    """Production-readiness checks, scheduler history and restore drills (agency admins only)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not is_agency_user(request.user):
            return _bad('Only agency admins can view system status.', status.HTTP_403_FORBIDDEN)
        from apps.core.diagnostics import run_all
        data = run_all()
        data['jobs'] = [{'job': r.job, 'status': r.status, 'started_at': r.started_at.isoformat(), 'error': r.error,
                         'duration_ms': int((r.finished_at - r.started_at).total_seconds() * 1000) if r.finished_at else None}
                        for r in JobRun.objects.all()[:25]]
        data['restore_drill'] = cache.get('restore-drill-result')
        return Response(data)

    def post(self, request):
        if not is_agency_user(request.user):
            return _bad('Only agency admins can run restore drills.', status.HTTP_403_FORBIDDEN)
        if request.data.get('action') != 'restore_drill':
            return _bad('Unknown action.')
        if not cache.add('restore-drill-lock', 1, 600):
            return _bad('A restore drill is already running.', status.HTTP_409_CONFLICT)
        cache.set('restore-drill-result', {'status': 'running', 'started_at': timezone.now().isoformat()}, 3600)

        def work():
            from django.db import close_old_connections
            from apps.core.backups import restore_drill
            try:
                result = restore_drill()
                result['status'] = 'passed' if result['ok'] else 'failed'
            except Exception as exc:
                result = {'status': 'failed', 'ok': False, 'steps': [{'step': 'error', 'ok': False, 'detail': type(exc).__name__}]}
            result['finished_at'] = timezone.now().isoformat()
            cache.set('restore-drill-result', result, 7 * 24 * 3600)
            cache.delete('restore-drill-lock')
            close_old_connections()
        if getattr(settings, 'GROWTH_SYNC_BACKGROUND', False):
            work()
        else:
            import threading
            threading.Thread(target=work, daemon=True).start()
        return Response({'status': 'started'}, status=status.HTTP_202_ACCEPTED)


class InstallCheckView(APIView):
    """Verify the chat is installed on the practice website (fetches only public pages)."""
    permission_classes = STAFF

    def post(self, request):
        practice, err = practice_or_404(request)
        if err:
            return err
        if not cache.add(f'install-check-{practice.id}', 1, 10):
            return _bad('A check just ran. Wait a few seconds and try again.', status.HTTP_429_TOO_MANY_REQUESTS)
        from .visibility import CheckError, install_check
        try:
            return Response(install_check(practice, str(request.data.get('url') or '')))
        except CheckError as exc:
            return _bad(str(exc))
