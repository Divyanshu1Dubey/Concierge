"""
URL routing for the emails app.
"""
from django.urls import path
from .views import (
    EmailThreadListView, EmailThreadDetailView,
    EmailListView, EmailSendView,
    EmailCadenceListView, EmailCadenceDetailView, InboundReplyCheckView,
)

urlpatterns = [
    path('threads/', EmailThreadListView.as_view(), name='email-thread-list'),
    path('threads/<uuid:id>/', EmailThreadDetailView.as_view(), name='email-thread-detail'),
    path('', EmailListView.as_view(), name='email-list'),
    path('send/', EmailSendView.as_view(), name='email-send'),
    path('inbound/check/', InboundReplyCheckView.as_view(), name='inbound-reply-check'),
    path('cadences/', EmailCadenceListView.as_view(), name='cadence-list'),
    path('cadences/<uuid:id>/', EmailCadenceDetailView.as_view(), name='cadence-detail'),
]
