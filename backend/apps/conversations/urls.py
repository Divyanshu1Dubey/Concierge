"""URL routing for conversations, chat, and widget endpoints."""
from django.urls import path
from .views import (
    ConversationListCreateView, ConversationDetailView,
    ConversationMessagesView, ConversationCloseView,
    ConversationEscalateView, ConversationStatsView,
    ChatView, WidgetConfigView, WidgetConversationInitView, WidgetSubmitView, HostedConciergeConfigView
)

urlpatterns = [
    path('', ConversationListCreateView.as_view(), name='conversation-list'),
    path('stats/', ConversationStatsView.as_view(), name='conversation-stats'),
    path('<uuid:id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    path('<uuid:id>/close/', ConversationCloseView.as_view(), name='conversation-close'),
    path('<uuid:id>/escalate/', ConversationEscalateView.as_view(), name='conversation-escalate'),
    path('<uuid:conversation_id>/messages/', ConversationMessagesView.as_view(), name='conversation-messages'),
    path('chat/', ChatView.as_view(), name='chat'),
    # Direct widget endpoints (when prefixed by api/v1/widget/)
    path('conversation/', WidgetConversationInitView.as_view(), name='widget-direct-conversation'),
    path('message/', ChatView.as_view(), name='widget-direct-message'),
    path('config/', WidgetConfigView.as_view(), name='widget-config-short'),
    path('widget/config/', WidgetConfigView.as_view(), name='widget-config'),
    path('widget/conversation/', WidgetConversationInitView.as_view(), name='widget-conversation-init'),
    path('widget/message/', ChatView.as_view(), name='widget-message'),
    path('widget/chat/', ChatView.as_view(), name='widget-chat'),
    path('widget/submit/', WidgetSubmitView.as_view(), name='widget-submit'),
    path('submit/', WidgetSubmitView.as_view(), name='widget-submit-short'),
    # Hosted concierge (accessible via api/concierge/ and api/v1/concierge/ prefixes)
    path('concierge/<slug:slug>/', HostedConciergeConfigView.as_view(), name='hosted-concierge-config'),
    path('<slug:slug>/', HostedConciergeConfigView.as_view(), name='hosted-concierge-config-short'),
]
