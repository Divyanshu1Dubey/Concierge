import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Practice",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=255, unique=True)),
                ("email", models.EmailField(max_length=254)),
                ("phone", models.CharField(max_length=20)),
                ("address", models.TextField()),
                ("city", models.CharField(default="Raleigh", max_length=100)),
                ("state", models.CharField(default="NC", max_length=2)),
                ("zip_code", models.CharField(default="27601", max_length=10)),
                (
                    "timezone",
                    models.CharField(default="America/New_York", max_length=50),
                ),
                ("website", models.URLField(blank=True)),
                ("logo_url", models.URLField(blank=True)),
                ("active", models.BooleanField(default=True)),
                ("api_key", models.CharField(blank=True, max_length=64, unique=True)),
                ("subscription_status", models.CharField(default="active", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Practice",
                "verbose_name_plural": "Practices",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Domain",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("hostname", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("CONNECTED", "Connected"),
                            ("PENDING", "Pending Verification"),
                            ("INVALID_DOMAIN", "Invalid Domain"),
                            ("DISABLED", "Disabled"),
                        ],
                        default="CONNECTED",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "practice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="domains",
                        to="practices.practice",
                    ),
                ),
            ],
            options={
                "ordering": ["hostname"],
                "unique_together": {("practice", "hostname")},
            },
        ),
        migrations.CreateModel(
            name="BookingRules",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("new_patient_duration", models.PositiveIntegerField(default=90)),
                ("doctor_duration", models.PositiveIntegerField(default=30)),
                ("hygiene_duration", models.PositiveIntegerField(default=60)),
                ("emergency_duration", models.PositiveIntegerField(default=60)),
                ("confirmation_hours", models.PositiveIntegerField(default=48)),
                (
                    "no_show_fee",
                    models.DecimalField(decimal_places=2, default=65.0, max_digits=8),
                ),
                (
                    "financing_options",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="List of financing options, e.g. ['Cherry', 'CareCredit']",
                    ),
                ),
                (
                    "business_hours",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Weekly business hours configuration: Mon-Sun {open: '08:00', close: '17:00', closed: false}",
                    ),
                ),
                (
                    "emergency_message",
                    models.TextField(
                        default="If you are experiencing severe pain, uncontrolled bleeding, or trauma, please call our emergency line immediately or visit an emergency room."
                    ),
                ),
                (
                    "after_hours_message",
                    models.TextField(
                        default="Our office is currently closed. Please leave your details and preferred time, and our front desk will coordinate your appointment first thing next business morning."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "practice",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="booking_rules",
                        to="practices.practice",
                    ),
                ),
            ],
            options={
                "verbose_name": "Booking Rules",
                "verbose_name_plural": "Booking Rules",
            },
        ),
        migrations.CreateModel(
            name="PracticeSettings",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("ai_enabled", models.BooleanField(default=True)),
                (
                    "ai_greeting_message",
                    models.TextField(
                        default="Hi! Welcome to {practice}. How can I help you today?"
                    ),
                ),
                ("ai_collects_phone", models.BooleanField(default=True)),
                (
                    "notification_mode",
                    models.CharField(
                        choices=[
                            ("EMAIL_DRAFT", "Email Draft"),
                            ("MANAGED_EMAIL", "HeyJarvis Managed Email"),
                            ("SMTP", "Custom SMTP"),
                        ],
                        default="MANAGED_EMAIL",
                        max_length=20,
                    ),
                ),
                ("default_from_name", models.CharField(blank=True, max_length=255)),
                ("default_from_email", models.EmailField(blank=True, max_length=254)),
                ("email_signature", models.TextField(blank=True)),
                ("notify_on_new_request", models.BooleanField(default=True)),
                ("notify_on_emergency", models.BooleanField(default=True)),
                ("notify_on_appointment", models.BooleanField(default=True)),
                ("notify_on_question", models.BooleanField(default=True)),
                ("notify_on_reschedule", models.BooleanField(default=True)),
                ("notify_on_cancel", models.BooleanField(default=True)),
                ("notify_on_handoff", models.BooleanField(default=True)),
                (
                    "notification_emails",
                    models.JSONField(
                        blank=True, default=dict, help_text="Email addresses to notify per intent"
                    ),
                ),
                ("follow_up_enabled", models.BooleanField(default=True)),
                (
                    "follow_up_intervals",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Hours between follow-up emails, e.g. [24, 48, 72]",
                    ),
                ),
                ("widget_title", models.CharField(default="HeyJarvis Concierge", max_length=100)),
                ("widget_subtitle", models.CharField(default="How can we help you today?", max_length=150)),
                ("widget_primary_color", models.CharField(default="#0d9488", max_length=10)),
                ("widget_position", models.CharField(default="right", max_length=10)),
                ("widget_auto_open", models.BooleanField(default=False)),
                ("widget_auto_open_delay_sec", models.PositiveIntegerField(default=5)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "practice",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="settings",
                        to="practices.practice",
                    ),
                ),
            ],
            options={
                "verbose_name": "Practice Settings",
                "verbose_name_plural": "Practice Settings",
            },
        ),
        migrations.CreateModel(
            name="EmailProvider",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "provider_type",
                    models.CharField(
                        choices=[("managed", "HeyJarvis Managed Email"), ("smtp", "Custom SMTP")],
                        default="managed",
                        max_length=20,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=True)),
                ("from_name", models.CharField(blank=True, max_length=255)),
                ("from_email", models.EmailField(blank=True, max_length=254)),
                ("reply_to", models.EmailField(blank=True, max_length=254)),
                ("smtp_host", models.CharField(blank=True, max_length=255)),
                ("smtp_port", models.PositiveIntegerField(blank=True, null=True)),
                ("smtp_username", models.CharField(blank=True, max_length=255)),
                ("smtp_password", models.TextField(blank=True)),
                ("smtp_use_tls", models.BooleanField(default=True)),
                ("smtp_use_ssl", models.BooleanField(default=False)),
                ("last_tested_at", models.DateTimeField(blank=True, null=True)),
                ("last_test_status", models.CharField(blank=True, max_length=20)),
                ("last_test_error", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "practice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_providers",
                        to="practices.practice",
                    ),
                ),
            ],
            options={
                "verbose_name": "Email Provider",
                "verbose_name_plural": "Email Providers",
            },
        ),
        migrations.CreateModel(
            name="EmailTemplate",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "template_type",
                    models.CharField(
                        choices=[
                            ("new_patient", "New Patient Request"),
                            ("emergency", "Emergency Request"),
                            ("cleaning", "Cleaning & Checkup"),
                            ("reschedule", "Reschedule Request"),
                            ("cancel", "Cancellation Request"),
                            ("question", "General Question"),
                            ("handoff", "Human Handoff Request"),
                        ],
                        max_length=50,
                    ),
                ),
                ("subject", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "practice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_templates",
                        to="practices.practice",
                    ),
                ),
            ],
            options={
                "ordering": ["template_type"],
                "unique_together": {("practice", "template_type")},
            },
        ),
    ]
