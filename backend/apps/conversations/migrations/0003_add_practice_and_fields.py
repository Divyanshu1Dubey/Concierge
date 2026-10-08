import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversations", "0002_initial"),
        ("practices", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="practice",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="conversations",
                to="practices.practice",
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="session_id",
            field=models.CharField(blank=True, db_index=True, max_length=100),
        ),
        migrations.AddField(
            model_name="conversation",
            name="state",
            field=models.CharField(
                choices=[
                    ("STARTED", "Started"),
                    ("IDENTIFYING_INTENT", "Identifying Intent"),
                    ("COLLECTING_INFORMATION", "Collecting Information"),
                    ("QUALIFYING", "Qualifying"),
                    ("CONFIRMING", "Confirming"),
                    ("SUBMITTING", "Submitting"),
                    ("SUBMITTED", "Submitted"),
                    ("HANDOFF", "Human Handoff"),
                    ("CLOSED", "Closed"),
                ],
                default="STARTED",
                max_length=35,
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="service_requested",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="conversation",
            name="preferred_date",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="conversation",
            name="preferred_time",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="conversation",
            name="urgency",
            field=models.CharField(
                choices=[
                    ("LOW", "Low"),
                    ("NORMAL", "Normal"),
                    ("HIGH", "High"),
                    ("URGENT", "Urgent"),
                ],
                default="NORMAL",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="lead_status",
            field=models.CharField(
                choices=[
                    ("NEW", "New"),
                    ("CONTACTED", "Contacted"),
                    ("QUALIFIED", "Qualified"),
                    ("BOOKED", "Booked"),
                    ("CLOSED", "Closed"),
                    ("SPAM", "Spam"),
                ],
                default="NEW",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="conversation",
            name="source_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="conversation",
            name="internal_notes",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="conversation",
            name="response_draft",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="conversation",
            name="response_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["practice", "status"], name="conv_practice_status_idx"),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["practice", "lead_status"], name="conv_practice_lead_idx"),
        ),
    ]
