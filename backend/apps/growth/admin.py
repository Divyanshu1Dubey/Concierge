from django.contrib import admin

from .models import (BriefingLog, ContactPreference, FollowUpTask, GrowthSettings, InquiryAttribution, Integration,
                     JobRun, RecallContact, SmsMessage, VisibilityReport)


@admin.register(FollowUpTask)
class FollowUpTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'practice', 'kind', 'status', 'due_at')
    list_filter = ('kind', 'status')


@admin.register(JobRun)
class JobRunAdmin(admin.ModelAdmin):
    list_display = ('job', 'status', 'started_at', 'finished_at', 'error')
    list_filter = ('job', 'status')


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ('practice', 'kind', 'status', 'last_checked_at')
    exclude = ('secret',)


for model in (GrowthSettings, InquiryAttribution, BriefingLog, VisibilityReport, ContactPreference, RecallContact, SmsMessage):
    admin.site.register(model)
