"""
Growth and conversion records: inquiry attribution, the follow-up queue, scheduled job runs,
weekly briefings, website visibility checks, contact preferences, recall lists, SMS and integrations.

Every table is keyed on a practice so tenant isolation works the same way as the rest of the app.
Nothing here sends to a patient on its own: patient-facing messages are drafted as follow-up tasks
and only go out when a staff member approves them.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class GrowthSettings(models.Model):
    """Per-practice switches for the conversion loop, outreach programs and the weekly briefing."""
    APPROVAL_EACH = 'approve_each'
    APPROVAL_BATCH = 'approve_batch'
    APPROVAL_CHOICES = [
        (APPROVAL_EACH, 'Staff review and send each message'),
        (APPROVAL_BATCH, 'Staff may approve several drafted messages at once'),
    ]

    practice = models.OneToOneField('practices.Practice', on_delete=models.CASCADE, related_name='growth_settings')

    # Conversion loop
    waiting_alert_hours = models.PositiveIntegerField(default=4)
    waiting_alerts_enabled = models.BooleanField(default=True)
    confirmation_nudge_hours = models.PositiveIntegerField(default=24)
    confirmation_nudges_enabled = models.BooleanField(default=True)
    approval_policy = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default=APPROVAL_EACH)

    # Weekly briefing for the doctor / practice admins (staff only)
    briefing_enabled = models.BooleanField(default=True)
    briefing_weekday = models.PositiveSmallIntegerField(default=0)  # 0 = Monday, practice timezone
    briefing_hour = models.PositiveSmallIntegerField(default=7)
    briefing_recipients = models.JSONField(default=list, blank=True)  # empty = practice admins

    # Outreach programs: off until a practice admin turns them on and accepts the notice.
    recall_enabled = models.BooleanField(default=False)
    recall_interval_months = models.PositiveSmallIntegerField(default=6)
    reactivation_enabled = models.BooleanField(default=False)
    reactivation_after_months = models.PositiveSmallIntegerField(default=18)
    review_requests_enabled = models.BooleanField(default=False)
    review_link = models.URLField(blank=True)
    outreach_acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    outreach_acknowledged_at = models.DateTimeField(null=True, blank=True)

    # Optional practice-entered figure, only used for clearly-labelled value estimates.
    average_visit_value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Growth settings for {self.practice_id}"

    @classmethod
    def for_practice(cls, practice):
        obj, _ = cls.objects.get_or_create(practice=practice)
        return obj


class InquiryAttribution(models.Model):
    """Where a website conversation came from (page, referrer, campaign tags), recorded when chat starts."""
    CHANNEL_CHOICES = [
        ('google_ads', 'Google Ads'),
        ('paid_social', 'Paid social'),
        ('google_business', 'Google Business Profile'),
        ('organic_search', 'Search engines'),
        ('ai_assistant', 'AI assistants'),
        ('social', 'Social media'),
        ('email', 'Email'),
        ('referral', 'Other websites'),
        ('campaign', 'Tagged campaign'),
        ('direct', 'Direct / unknown'),
    ]

    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='inquiry_attributions')
    conversation = models.OneToOneField(
        'conversations.Conversation', on_delete=models.CASCADE, related_name='attribution')
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='direct', db_index=True)
    landing_path = models.CharField(max_length=300, blank=True)
    referrer_host = models.CharField(max_length=200, blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=150, blank=True)
    has_click_id = models.BooleanField(default=False)  # gclid / fbclid / msclkid present
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['practice', 'created_at'])]


class FollowUpTask(models.Model):
    """
    One thing the front desk should do. Tasks are created by the scheduler (or staff) and may carry a
    drafted message; drafts are never sent until a staff member approves them.
    """
    KIND_WAITING_REPLY = 'waiting_reply'
    KIND_PATIENT_REPLIED = 'patient_replied'
    KIND_UNCONFIRMED = 'unconfirmed_offer'
    KIND_RESCHEDULE = 'reschedule_requested'
    KIND_RECALL = 'recall_due'
    KIND_REACTIVATION = 'reactivation'
    KIND_REVIEW = 'review_request'
    KIND_MANUAL = 'manual'
    KIND_REVIEW_REPLY = 'review_reply'
    KIND_CHOICES = [
        (KIND_WAITING_REPLY, 'Patient waiting for a reply'),
        (KIND_PATIENT_REPLIED, 'Patient replied and is waiting'),
        (KIND_UNCONFIRMED, 'Visit time not confirmed yet'),
        (KIND_RESCHEDULE, 'Patient asked for another time'),
        (KIND_RECALL, 'Recall visit due'),
        (KIND_REACTIVATION, 'Patient not seen in a while'),
        (KIND_REVIEW, 'Ask for a review'),
        (KIND_MANUAL, 'Follow-up'),
        (KIND_REVIEW_REPLY, 'Reply to a Google review'),
    ]
    OUTREACH_KINDS = (KIND_RECALL, KIND_REACTIVATION, KIND_REVIEW)

    STATUS_OPEN = 'open'
    STATUS_SNOOZED = 'snoozed'
    STATUS_DONE = 'done'
    STATUS_SENT = 'sent'
    STATUS_DISMISSED = 'dismissed'
    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_SNOOZED, 'Snoozed'),
        (STATUS_DONE, 'Done'),
        (STATUS_SENT, 'Message sent'),
        (STATUS_DISMISSED, 'Dismissed'),
    ]
    CHANNEL_CHOICES = [('email', 'Email'), ('sms', 'Text message'), ('phone', 'Phone call'), ('google', 'Public Google reply')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='follow_up_tasks')
    kind = models.CharField(max_length=24, choices=KIND_CHOICES, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    appointment = models.ForeignKey(
        'appointments.Appointment', null=True, blank=True, on_delete=models.CASCADE, related_name='follow_up_tasks')
    recall_contact = models.ForeignKey(
        'growth.RecallContact', null=True, blank=True, on_delete=models.CASCADE, related_name='tasks')
    patient_name = models.CharField(max_length=200, blank=True)
    patient_email = models.EmailField(blank=True)
    patient_phone = models.CharField(max_length=30, blank=True)
    title = models.CharField(max_length=200)
    reason = models.CharField(max_length=400, blank=True)
    channel = models.CharField(max_length=8, choices=CHANNEL_CHOICES, default='email')
    draft_subject = models.CharField(max_length=200, blank=True)
    draft_body = models.TextField(blank=True, max_length=5000)
    draft_source = models.CharField(max_length=12, blank=True)  # template / ai / staff
    due_at = models.DateTimeField(default=timezone.now, db_index=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=120)
    alert_sent_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    completed_at = models.DateTimeField(null=True, blank=True)
    result_note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['due_at']
        constraints = [models.UniqueConstraint(fields=['practice', 'dedupe_key'], name='uniq_followup_dedupe')]
        indexes = [models.Index(fields=['practice', 'status', 'due_at'])]

    def __str__(self):
        return f"{self.get_kind_display()} - {self.patient_name or self.patient_email}"


class JobRun(models.Model):
    """A scheduled job execution. The unique key makes a repeated cron call for the same window a no-op."""
    job = models.CharField(max_length=60, db_index=True)
    run_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=12, default='running')  # running / ok / failed
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-started_at']


class BriefingLog(models.Model):
    """One weekly practice briefing (unique per practice and week)."""
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='briefings')
    week_start = models.DateField()
    recipients = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, default='sent')  # sending / sent / failed
    error = models.CharField(max_length=300, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-week_start']
        constraints = [models.UniqueConstraint(fields=['practice', 'week_start'], name='uniq_briefing_week')]


class VisibilityReport(models.Model):
    """Result of a one-click website check against the practice's approved facts."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='visibility_reports')
    url = models.URLField(max_length=500)
    status = models.CharField(max_length=12, default='ok')  # ok / failed
    error = models.CharField(max_length=300, blank=True)
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    lighthouse = models.JSONField(default=dict, blank=True)
    findings = models.JSONField(default=list, blank=True)
    facts = models.JSONField(default=dict, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']


class ContactPreference(models.Model):
    """Opt-outs (and recorded consent) per practice, channel and address. Checked before any outreach."""
    CHANNEL_CHOICES = [('email', 'Email'), ('sms', 'Text message')]
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='contact_preferences')
    channel = models.CharField(max_length=6, choices=CHANNEL_CHOICES)
    address = models.CharField(max_length=254)  # lower-cased email or E.164 phone
    opted_out = models.BooleanField(default=False)
    opted_out_at = models.DateTimeField(null=True, blank=True)
    source = models.CharField(max_length=40, blank=True)  # unsubscribe_link / sms_stop / staff
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['practice', 'channel', 'address'], name='uniq_contact_pref')]


class RecallContact(models.Model):
    """A patient on the practice's recall list (imported CSV, a completed request, or a future PMS sync)."""
    STATUS_CHOICES = [('active', 'Active'), ('scheduled', 'Scheduled'), ('inactive', 'Inactive')]
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='recall_contacts')
    name = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    last_visit = models.DateField(null=True, blank=True)
    next_due = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    consent_outreach = models.BooleanField(default=False)
    source = models.CharField(max_length=20, default='import')
    external_id = models.CharField(max_length=80, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_due', 'name']
        indexes = [models.Index(fields=['practice', 'email']), models.Index(fields=['practice', 'phone'])]

    def __str__(self):
        return self.name


class SmsMessage(models.Model):
    """A text message sent to or received from a patient through the configured SMS provider."""
    DIRECTION_CHOICES = [('out', 'Outgoing'), ('in', 'Incoming')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='sms_messages')
    appointment = models.ForeignKey(
        'appointments.Appointment', null=True, blank=True, on_delete=models.SET_NULL, related_name='sms_messages')
    direction = models.CharField(max_length=3, choices=DIRECTION_CHOICES)
    to_number = models.CharField(max_length=20)
    from_number = models.CharField(max_length=20, blank=True)
    body = models.TextField(max_length=1600)
    status = models.CharField(max_length=12, default='queued')  # queued / sent / failed / received / blocked
    provider = models.CharField(max_length=20, blank=True)
    provider_id = models.CharField(max_length=64, blank=True)
    error = models.CharField(max_length=300, blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']


class Integration(models.Model):
    """A per-practice connection to an outside service. Secrets are stored encrypted and never returned."""
    KIND_CHOICES = [
        ('google_business', 'Google Business Profile'),
        ('nexhealth', 'NexHealth (practice management sync)'),
        ('twilio', 'Twilio SMS'),
    ]
    STATUS_CHOICES = [
        ('not_connected', 'Not connected'),
        ('pending', 'Waiting for authorization'),
        ('connected', 'Connected'),
        ('error', 'Needs attention'),
    ]
    practice = models.ForeignKey('practices.Practice', on_delete=models.CASCADE, related_name='integrations')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES, default='not_connected')
    config = models.JSONField(default=dict, blank=True)  # non-secret settings (ids, selected location)
    secret = models.TextField(blank=True)  # encrypted JSON (tokens / keys)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=300, blank=True)
    connected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['practice', 'kind'], name='uniq_practice_integration')]
