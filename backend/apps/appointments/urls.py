"""URL routing for appointments and front-desk workflows."""
from django.urls import path
from .views import (
    AppointmentListCreateView, AppointmentDetailView, AppointmentStatsView,
    AIDraftView, SaveDraftView, SendReplyView, AddInternalNoteView,
    UpdateRequestStatusView, ServiceListView, AvailableSlotsView
)

urlpatterns = [
    path('', AppointmentListCreateView.as_view(), name='appointment-list'),
    path('stats/', AppointmentStatsView.as_view(), name='appointment-stats'),
    path('services/', ServiceListView.as_view(), name='service-list'),
    path('slots/', AvailableSlotsView.as_view(), name='slot-list'),
    path('<uuid:id>/', AppointmentDetailView.as_view(), name='appointment-detail'),
    path('<uuid:id>/ai-draft/', AIDraftView.as_view(), name='appointment-ai-draft'),
    path('<uuid:id>/save-draft/', SaveDraftView.as_view(), name='appointment-save-draft'),
    path('<uuid:id>/send-reply/', SendReplyView.as_view(), name='appointment-send-reply'),
    path('<uuid:id>/respond/', SendReplyView.as_view(), name='appointment-respond'),
    path('<uuid:id>/notes/', AddInternalNoteView.as_view(), name='appointment-add-note'),
    path('<uuid:id>/status/', UpdateRequestStatusView.as_view(), name='appointment-update-status'),
]
