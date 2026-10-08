"""Practices app models - Tenant architecture, rules, domains, templates, and audit logs."""
import secrets
from django.db import models
from django.conf import settings
from apps.core.security import encrypt_secret, decrypt_secret, redact_dict


class Practice(models.Model):
    """Dental practice entity - the tenant root."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    address = models.TextField()
    city = models.CharField(max_length=100, default='Raleigh')
    state = models.CharField(max_length=2, default='NC')
    zip_code = models.CharField(max_length=10, default='27601')
    timezone = models.CharField(max_length=50, default='America/New_York')
    website = models.URLField(blank=True)
    logo_url = models.URLField(blank=True)
    active = models.BooleanField(default=True)
    api_key = models.CharField(max_length=64, unique=True, blank=True)
    subscription_status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Practice'
        verbose_name_plural = 'Practices'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.api_key:
            self.api_key = secrets.token_hex(32)
        super().save(*args, **kwargs)

    @property
    def client_key(self):
        return self.api_key

    @property
    def full_address(self):
        return f"{self.address}, {self.city}, {self.state} {self.zip_code}"

    def regenerate_api_key(self, actor=None, ip_address=None):
        """Regenerate the public client key and log audit event."""
        old_key = self.api_key
        self.api_key = secrets.token_hex(32)
        self.save(update_fields=['api_key', 'updated_at'])
        AuditLog.objects.create(
            practice=self,
            actor=actor,
            action='CLIENT_KEY_REGENERATED',
            details={'message': 'Existing website installations using old key invalidated.'},
            ip_address=ip_address
        )
        return self.api_key

    @property
    def allowed_domains_list(self):
        """Return list of allowed hostnames for origin validation."""
        domains = list(self.domains.filter(status='CONNECTED').values_list('hostname', flat=True))
        if self.website:
            from urllib.parse import urlparse
            h = urlparse(self.website).hostname
            if h and h not in domains:
                domains.append(h)
        return domains


class Domain(models.Model):
    """Allowed website domain for tenant widget origin validation."""
    STATUS_CHOICES = [
        ('PENDING', 'Pending Verification'),
        ('CONNECTED', 'Connected'),
        ('INVALID_DOMAIN', 'Invalid Domain'),
        ('DISABLED', 'Disabled'),
    ]

    practice = models.ForeignKey(Practice, on_delete=models.CASCADE, related_name='domains')
    hostname = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CONNECTED')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('practice', 'hostname')
        ordering = ['hostname']

    def __str__(self):
        return f"{self.hostname} ({self.status}) - {self.practice.name}"


class BookingRules(models.Model):
    """Practice-specific booking rules and configurations."""

    practice = models.OneToOneField(
        Practice, on_delete=models.CASCADE, related_name='booking_rules'
    )

    # Durations in minutes
    new_patient_duration = models.PositiveIntegerField(default=90)
    doctor_duration = models.PositiveIntegerField(default=30)
    hygiene_duration = models.PositiveIntegerField(default=60)
    emergency_duration = models.PositiveIntegerField(default=60)

    # Confirmation settings
    confirmation_hours = models.PositiveIntegerField(default=48)

    # No-show fee
    no_show_fee = models.DecimalField(max_digits=8, decimal_places=2, default=65.00)

    # Financing options
    financing_options = models.JSONField(
        default=dict,
        blank=True,
        help_text="List of financing options, e.g. ['Cherry', 'CareCredit']"
    )

    # Business hours (stored as JSON)
    business_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Weekly business hours configuration: Mon-Sun {open: '08:00', close: '17:00', closed: false}"
    )

    # Emergency and after-hours messages
    emergency_message = models.TextField(
        default="If you are experiencing severe pain, uncontrolled bleeding, or trauma, please call our emergency line immediately or visit an emergency room."
    )
    after_hours_message = models.TextField(
        default="Our office is currently closed. Please leave your details and preferred time, and our front desk will coordinate your appointment first thing next business morning."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Booking Rules'
        verbose_name_plural = 'Booking Rules'

    def __str__(self):
        return f"Booking Rules - {self.practice.name}"


class PracticeSettings(models.Model):
    """Additional practice configuration settings."""

    practice = models.OneToOneField(
        Practice, on_delete=models.CASCADE, related_name='settings'
    )

    # AI settings
    ai_enabled = models.BooleanField(default=True)
    ai_greeting_message = models.TextField(
        default="Hi! Welcome to {practice}. How can I help you today?"
    )
    ai_collects_phone = models.BooleanField(default=True)

    # Email notification modes: EMAIL_DRAFT, MANAGED_EMAIL, SMTP
    notification_mode = models.CharField(
        max_length=20,
        choices=[
            ('EMAIL_DRAFT', 'Email Draft'),
            ('MANAGED_EMAIL', 'HeyJarvis Managed Email'),
            ('SMTP', 'Custom SMTP'),
        ],
        default='MANAGED_EMAIL'
    )

    default_from_name = models.CharField(max_length=255, blank=True)
    default_from_email = models.EmailField(blank=True)
    email_signature = models.TextField(blank=True)

    # Notification settings by intent
    notify_on_new_request = models.BooleanField(default=True)
    notify_on_emergency = models.BooleanField(default=True)
    notify_on_appointment = models.BooleanField(default=True)
    notify_on_question = models.BooleanField(default=True)
    notify_on_reschedule = models.BooleanField(default=True)
    notify_on_cancel = models.BooleanField(default=True)
    notify_on_handoff = models.BooleanField(default=True)
    notify_on_patient_reply = models.BooleanField(default=True)

    notification_emails = models.JSONField(
        default=dict,
        blank=True,
        help_text="Email addresses to notify per intent: {general: '...', emergency: '...'}"
    )

    # Follow-up cadence settings
    follow_up_enabled = models.BooleanField(default=True)
    follow_up_intervals = models.JSONField(
        default=dict,
        blank=True,
        help_text="Hours between follow-up emails, e.g. [24, 48, 72]"
    )

    # Widget appearance customization
    widget_title = models.CharField(max_length=100, default='HeyJarvis Concierge')
    widget_subtitle = models.CharField(max_length=150, default='How can we help you today?')
    widget_primary_color = models.CharField(max_length=10, default='#0d9488')
    widget_position = models.CharField(max_length=10, default='right') # 'left' or 'right'
    widget_auto_open = models.BooleanField(default=False)
    widget_auto_open_delay_sec = models.PositiveIntegerField(default=5)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Practice Settings'
        verbose_name_plural = 'Practice Settings'

    def __str__(self):
        return f"Settings - {self.practice.name}"


class EmailProvider(models.Model):
    """Email provider configuration for a practice."""

    PROVIDER_CHOICES = [
        ('managed', 'HeyJarvis Managed Email'),
        ('smtp', 'Custom SMTP'),
    ]

    practice = models.ForeignKey(
        Practice, on_delete=models.CASCADE, related_name='email_providers'
    )
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default='managed')
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=True)

    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(blank=True)
    reply_to = models.EmailField(blank=True)

    # SMTP fields (password encrypted at rest)
    smtp_host = models.CharField(max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(null=True, blank=True)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password = models.TextField(blank=True)
    smtp_use_tls = models.BooleanField(default=True)
    smtp_use_ssl = models.BooleanField(default=False)

    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=20, blank=True) # SUCCESS, FAILED
    last_test_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Email Provider'
        verbose_name_plural = 'Email Providers'

    def set_smtp_password(self, raw_password: str):
        """Encrypt password before persisting."""
        self.smtp_password = encrypt_secret(raw_password)

    def get_smtp_password(self) -> str:
        """Decrypt password for sending email."""
        return decrypt_secret(self.smtp_password)

    def test_connection(self) -> dict:
        """Safely test connection to SMTP server."""
        import smtplib
        from django.utils import timezone
        
        if self.provider_type == 'managed':
            self.last_tested_at = timezone.now()
            self.last_test_status = 'SUCCESS'
            self.last_test_error = ''
            self.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_error'])
            return {'success': True, 'message': 'HeyJarvis Managed Email provider is active and ready.'}

        if not self.smtp_host or not self.smtp_port:
            return {'success': False, 'message': 'SMTP host and port are required.'}

        try:
            pwd = self.get_smtp_password()
            if self.smtp_use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                if self.smtp_use_tls:
                    server.starttls()

            if self.smtp_username and pwd:
                server.login(self.smtp_username, pwd)

            server.quit()
            self.last_tested_at = timezone.now()
            self.last_test_status = 'SUCCESS'
            self.last_test_error = ''
            self.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_error'])
            return {'success': True, 'message': 'SMTP connection and authentication successful!'}
        except Exception as e:
            self.last_tested_at = timezone.now()
            self.last_test_status = 'FAILED'
            self.last_test_error = str(e)
            self.save(update_fields=['last_tested_at', 'last_test_status', 'last_test_error'])
            return {'success': False, 'message': f"SMTP connection failed: {str(e)}"}


class EmailTemplate(models.Model):
    """Customizable tenant email templates with token support."""
    TEMPLATE_TYPES = [
        ('new_patient', 'New Patient Request'),
        ('emergency', 'Emergency Request'),
        ('cleaning', 'Cleaning & Checkup'),
        ('reschedule', 'Reschedule Request'),
        ('cancel', 'Cancellation Request'),
        ('question', 'General Question'),
        ('handoff', 'Human Handoff Request'),
    ]

    practice = models.ForeignKey(Practice, on_delete=models.CASCADE, related_name='email_templates')
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('practice', 'template_type')
        ordering = ['template_type']

    def __str__(self):
        return f"{self.get_template_type_display()} - {self.practice.name}"

    def render(self, context: dict) -> tuple[str, str]:
        """Render subject and body with provided context variables."""
        subj = self.subject
        body = self.body
        for k, v in context.items():
            token = f"{{{{{k}}}}}"
            subj = subj.replace(token, str(v or ''))
            body = body.replace(token, str(v or ''))
        return subj, body


class AuditLog(models.Model):
    """Audit log for security, settings changes, key rotations, and actions."""
    practice = models.ForeignKey(Practice, on_delete=models.CASCADE, related_name='audit_logs')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_entries'
    )
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} on {self.practice.name} at {self.created_at}"
