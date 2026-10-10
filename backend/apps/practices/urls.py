"""URL routing for practices, tenant settings, team, and integrations."""
from django.urls import path
from .views import (
    CurrentTenantView, RegenerateClientKeyView, DomainListCreateView, DomainDeleteView,
    BookingRulesView, TenantSettingsView, EmailConfigView, TestEmailConnectionView,
    EmailTemplateListView, EmailTemplateDetailView, TeamListView, TeamMemberDetailView,
    AuditLogListView, TenantMetricsView, WordPressDownloadView, ExportDataView,
    AgencyPracticeListView, AgencyPracticeToggleStatusView,
    AgencyPracticeUsersView, AgencyPracticeUserActionView, AgencyPracticeIntegrationView,
    AccessRequestCreateView, AccessRequestListView, AccessRequestDetailView,
)

urlpatterns = [
    path('', CurrentTenantView.as_view(), name='tenant-detail'),
    path('all/', AgencyPracticeListView.as_view(), name='agency-practice-list'),
    path('access-requests/', AccessRequestListView.as_view(), name='access-request-list'),
    path('access-requests/new/', AccessRequestCreateView.as_view(), name='access-request-create'),
    path('access-requests/<int:id>/', AccessRequestDetailView.as_view(), name='access-request-detail'),
    path('<int:id>/toggle-status/', AgencyPracticeToggleStatusView.as_view(), name='agency-practice-toggle'),
    path('<int:practice_id>/users/', AgencyPracticeUsersView.as_view(), name='agency-practice-users'),
    path('<int:practice_id>/users/<uuid:user_id>/action/', AgencyPracticeUserActionView.as_view(), name='agency-practice-user-action'),
    path('<int:practice_id>/integration/', AgencyPracticeIntegrationView.as_view(), name='agency-practice-integration'),
    path('metrics/', TenantMetricsView.as_view(), name='tenant-metrics'),
    path('key/regenerate/', RegenerateClientKeyView.as_view(), name='tenant-key-regenerate'),
    path('domains/', DomainListCreateView.as_view(), name='tenant-domains'),
    path('domains/<int:id>/', DomainDeleteView.as_view(), name='tenant-domain-delete'),
    path('booking-rules/', BookingRulesView.as_view(), name='tenant-booking-rules'),
    path('settings/', TenantSettingsView.as_view(), name='tenant-settings'),
    path('email-config/', EmailConfigView.as_view(), name='tenant-email-config'),
    path('email-config/test/', TestEmailConnectionView.as_view(), name='tenant-email-test'),
    path('templates/', EmailTemplateListView.as_view(), name='tenant-templates'),
    path('templates/<int:id>/', EmailTemplateDetailView.as_view(), name='tenant-template-detail'),
    path('team/', TeamListView.as_view(), name='tenant-team'),
    path('team/<uuid:id>/', TeamMemberDetailView.as_view(), name='tenant-team-detail'),
    path('audit-logs/', AuditLogListView.as_view(), name='tenant-audit-logs'),
    path('integration/wordpress/', WordPressDownloadView.as_view(), name='tenant-wordpress-download'),
    path('<int:tenant_id>/integration/wordpress/', WordPressDownloadView.as_view(), name='tenant-wordpress-download-id'),
    path('export/<str:export_type>/', ExportDataView.as_view(), name='tenant-export'),
]
