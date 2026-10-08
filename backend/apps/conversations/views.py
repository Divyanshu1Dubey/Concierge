"""Views for the conversations app with Multi-Tenant isolation, State Machine processing, and Public Widget endpoints."""
import logging
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone

from .models import Conversation, Message
from .serializers import (
    ConversationSerializer, ConversationCreateSerializer,
    ChatRequestSerializer, ChatResponseSerializer, MessageSerializer,
)
from apps.core.permissions import TenantIsolationMixin, IsTenantViewer, IsTenantMember
from apps.core.security import is_allowed_origin
from apps.practices.models import Practice
from .state_machine import ConciergeStateMachine, QUICK_REPLIES_MAP

logger = logging.getLogger(__name__)


def resolve_practice(request, data: dict = None) -> Practice | None:
    """Resolve practice from client_key, X-Client-Key, practice_slug, or fallback."""
    data = data or {}
    client_key = (
        data.get('client_key') or
        request.headers.get('X-Client-Key') or
        request.query_params.get('client_key') or
        request.query_params.get('api_key')
    )
    if client_key:
        return Practice.objects.filter(api_key=client_key, active=True).first()

    slug = data.get('practice_slug') or request.query_params.get('practice_slug') or request.query_params.get('slug')
    if slug:
        p = Practice.objects.filter(slug=slug, active=True).first()
        if p:
            return p
        for part in slug.replace('_', '-').split('-'):
            if len(part) >= 3:
                p = Practice.objects.filter(slug__icontains=part, active=True).first()
                if p:
                    return p
        return None

    # Fallback to first practice only if neither key nor slug specified
    return Practice.objects.filter(active=True).first()


class ConversationListCreateView(TenantIsolationMixin, generics.ListCreateAPIView):
    """List conversations for the current tenant practice or create a new one."""
    queryset = Conversation.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]
    filterset_fields = ['status', 'intent', 'assigned_to', 'lead_status', 'urgency']
    search_fields = ['patient_email', 'patient_name', 'patient_phone', 'service_requested']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return ConversationCreateSerializer
        return ConversationSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        lead_filter = self.request.query_params.get('lead_status')
        if lead_filter:
            qs = qs.filter(lead_status=lead_filter)
        urgency_filter = self.request.query_params.get('urgency')
        if urgency_filter:
            qs = qs.filter(urgency=urgency_filter)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient_email__icontains=search) |
                Q(patient_name__icontains=search) |
                Q(patient_phone__icontains=search) |
                Q(service_requested__icontains=search)
            )
        return qs


class ConversationDetailView(generics.RetrieveUpdateAPIView):
    """Get or update a conversation with tenant security check."""
    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.practice:
            return Conversation.objects.filter(practice=user.practice)
        return Conversation.objects.none()

    def perform_update(self, serializer):
        serializer.save()
        conversation = serializer.instance
        conversation.last_activity_at = timezone.now()
        conversation.save(update_fields=['last_activity_at'])


class ConversationCloseView(APIView):
    """Mark a conversation as closed."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        conv = get_object_or_404(Conversation, id=id, practice=request.user.practice)
        conv.status = Conversation.STATUS_CLOSED
        conv.state = Conversation.STATE_CLOSED
        conv.ended_at = timezone.now()
        conv.save(update_fields=['status', 'state', 'ended_at'])
        return Response({'status': 'closed', 'id': str(conv.id)})


class ConversationEscalateView(APIView):
    """Mark a conversation for human staff escalation."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        conv = get_object_or_404(Conversation, id=id, practice=request.user.practice)
        conv.status = Conversation.STATUS_HANDOFF
        conv.state = Conversation.STATE_HANDOFF
        conv.urgency = 'HIGH'
        conv.save(update_fields=['status', 'state', 'urgency'])
        return Response({'status': 'escalated', 'id': str(conv.id)})


class ConversationStatsView(APIView):
    """Summary statistics for tenant conversations."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = request.user.practice
        if not practice:
            return Response({'total': 0, 'active': 0, 'completed': 0, 'handoff': 0})

        qs = Conversation.objects.filter(practice=practice)
        total = qs.count()
        active = qs.filter(status=Conversation.STATUS_ACTIVE).count()
        completed = qs.filter(status=Conversation.STATUS_COMPLETED).count()
        handoff = qs.filter(status=Conversation.STATUS_HANDOFF).count()
        urgent = qs.filter(urgency='URGENT').count()

        return Response({
            'total': total,
            'active': active,
            'completed': completed,
            'handoff': handoff,
            'urgent': urgent,
        })


class ConversationMessagesView(generics.ListAPIView):
    """List messages for a conversation with tenant verification."""
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get_queryset(self):
        conversation_id = self.kwargs.get('conversation_id')
        user = self.request.user
        return Message.objects.filter(
            conversation_id=conversation_id,
            conversation__practice=user.practice
        ).order_by('created_at')


class WidgetConfigView(APIView):
    """Public endpoint returning tenant styling, hours, and configuration for widget embed."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        practice = resolve_practice(request)
        if not practice:
            return Response({'error': 'Practice not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

        # Validate origin against allowed domains
        origin = request.headers.get('Origin') or request.headers.get('Referer')
        if not is_allowed_origin(origin, practice.allowed_domains_list):
            return Response(
                {'error': 'Origin domain not authorized for this client key'},
                status=status.HTTP_403_FORBIDDEN
            )

        ps = getattr(practice, 'settings', None)
        br = getattr(practice, 'booking_rules', None)

        from .state_machine import is_office_open
        is_open, after_hours_msg = is_office_open(practice)

        return Response({
            'practice_name': practice.name,
            'practice_slug': practice.slug,
            'phone': practice.phone,
            'email': practice.email,
            'address': practice.full_address,
            'timezone': practice.timezone,
            'title': getattr(ps, 'widget_title', 'HeyJarvis Concierge'),
            'subtitle': getattr(ps, 'widget_subtitle', 'How can we help you today?'),
            'primary_color': getattr(ps, 'widget_primary_color', '#0d9488'),
            'position': getattr(ps, 'widget_position', 'right'),
            'auto_open': getattr(ps, 'widget_auto_open', False),
            'auto_open_delay': getattr(ps, 'widget_auto_open_delay_sec', 5),
            'greeting': getattr(ps, 'ai_greeting_message', f"Welcome to {practice.name}! How may I help you?").replace('{practice}', practice.name),
            'is_open': is_open,
            'after_hours_message': after_hours_msg,
            'quick_replies': QUICK_REPLIES_MAP['INITIAL'],
        })


class WidgetConversationInitView(APIView):
    """Initialize a conversation session from widget.js."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        practice = resolve_practice(request, request.data)
        if not practice:
            return Response({'error': 'Practice not found'}, status=status.HTTP_404_NOT_FOUND)

        session_id = request.data.get('session_id', '')
        conv = None
        if session_id:
            conv = Conversation.objects.filter(session_id=session_id, practice=practice).first()

        if not conv:
            conv = Conversation.objects.create(
                practice=practice,
                session_id=session_id,
                state=Conversation.STATE_IDENTIFYING_INTENT,
            )

        ps = getattr(practice, 'settings', None)
        from .state_machine import is_office_open
        is_open, after_hours_msg = is_office_open(practice)

        greeting = getattr(ps, 'ai_greeting_message', f"Welcome to {practice.name}! How may I help you?").replace('{practice}', practice.name)
        if not is_open and after_hours_msg:
            greeting += f"\n\n({after_hours_msg})"

        return Response({
            'session_id': session_id,
            'conversation_id': str(conv.id),
            'welcome_message': greeting,
            'message': greeting,
            'response': greeting,
            'quick_replies': QUICK_REPLIES_MAP['INITIAL'],
            'ask_name': True,
            'state': conv.state,
        })


class ChatView(generics.GenericAPIView):

    """Public chat endpoint supporting both widget and hosted Concierge sessions."""
    permission_classes = [permissions.AllowAny]
    serializer_class = ChatRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        practice = resolve_practice(request, data)
        if not practice:
            return Response({'error': 'Practice not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

        # Validate origin
        origin = request.headers.get('Origin') or request.headers.get('Referer') or data.get('url')
        if not is_allowed_origin(origin, practice.allowed_domains_list):
            return Response({'error': 'Domain not authorized for this widget key'}, status=status.HTTP_403_FORBIDDEN)

        user_message_text = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        # Get or create conversation
        if conversation_id:
            conversation = get_object_or_404(Conversation, id=conversation_id, practice=practice)
        elif data.get('session_id'):
            conversation = Conversation.objects.filter(session_id=data.get('session_id'), practice=practice).order_by('-started_at').first()
            if not conversation:
                conversation = Conversation.objects.create(
                    practice=practice,
                    session_id=data.get('session_id', ''),
                    patient_email=data.get('email', ''),
                    patient_name=data.get('name', ''),
                    patient_phone=data.get('phone', ''),
                    source_url=data.get('url', ''),
                    state=Conversation.STATE_STARTED,
                )
        else:
            conversation = Conversation.objects.create(
                practice=practice,
                session_id=data.get('session_id', ''),
                patient_email=data.get('email', ''),
                patient_name=data.get('name', ''),
                patient_phone=data.get('phone', ''),
                source_url=data.get('url', ''),
                state=Conversation.STATE_STARTED,
            )

        # Record user message if non-empty
        if user_message_text:
            Message.objects.create(
                conversation=conversation,
                sender='user',
                content=user_message_text,
            )

        # Process through state machine
        from apps.ai_service.engine import AIEngine
        try:
            ai_engine = AIEngine()
        except Exception:
            ai_engine = None

        sm = ConciergeStateMachine(conversation=conversation, practice=practice, ai_engine=ai_engine)
        step_result = sm.process_message(user_message_text or "Hello")

        # Record AI reply message
        ai_reply = Message.objects.create(
            conversation=conversation,
            sender='ai',
            content=step_result.get('message', ''),
            intent=step_result.get('intent', 'general_chat'),
        )

        reply_text = step_result.get('message', '')
        # Return standardized response
        return Response({
            'conversation_id': str(conversation.id),
            'message': reply_text,
            'response': reply_text,
            'welcome_message': reply_text,
            'state': step_result.get('state', conversation.state),
            'intent': step_result.get('intent', conversation.intent),
            'conversation_complete': step_result.get('conversation_complete', False),
            'quick_replies': step_result.get('quick_replies', []),
            'requires_human': step_result.get('requires_human', False),
        }, status=status.HTTP_200_OK)


class WidgetSubmitView(APIView):
    """Finalize widget appointment submission."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        practice = resolve_practice(request, request.data)
        if not practice:
            return Response({'error': 'Practice not found'}, status=status.HTTP_404_NOT_FOUND)

        conv_id = request.data.get('conversation_id')
        conv = None
        if conv_id:
            conv = Conversation.objects.filter(id=conv_id, practice=practice).first()

        name = request.data.get('patient_name') or (conv.patient_name if conv else 'Guest')
        phone = request.data.get('patient_phone') or (conv.patient_phone if conv else '')
        email = request.data.get('patient_email') or (conv.patient_email if conv else '')
        date = request.data.get('preferred_date') or (conv.preferred_date if conv else '')
        time = request.data.get('preferred_time') or (conv.preferred_time if conv else '')

        from apps.appointments.models import Appointment, Service
        srv = Service.objects.filter(practice=practice).first()

        appt = Appointment.objects.create(
            practice=practice,
            service=srv,
            conversation=conv,
            patient_name=name,
            patient_phone=phone,
            patient_email=email,
            preferred_date=date,
            preferred_time=time,
            status='pending',
            source_website=request.data.get('url', ''),
            message=request.data.get('notes', ''),
            ai_summary=f"Direct appointment request from widget: {name} for {date} ({time})."
        )

        if conv:
            conv.state = Conversation.STATE_SUBMITTED
            conv.status = Conversation.STATUS_COMPLETED
            conv.save(update_fields=['state', 'status'])

        return Response({
            'status': 'submitted',
            'confirmation_code': appt.confirmation_code,
            'response': f"Your request has been submitted to {practice.name}! Our front desk will contact you to coordinate your visit.",
        })


class HostedConciergeConfigView(APIView):
    """Retrieve hosted concierge configuration by practice slug."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        practice = get_object_or_404(Practice, slug=slug, active=True)
        ps = getattr(practice, 'settings', None)

        from .state_machine import is_office_open
        is_open, after_hours_msg = is_office_open(practice)

        return Response({
            'practice_name': practice.name,
            'practice_slug': practice.slug,
            'client_key': practice.api_key,
            'phone': practice.phone,
            'email': practice.email,
            'address': practice.full_address,
            'website': practice.website,
            'logo_url': practice.logo_url,
            'title': getattr(ps, 'widget_title', 'HeyJarvis Concierge'),
            'greeting': getattr(ps, 'ai_greeting_message', f"Welcome to {practice.name}! How may I help you?").replace('{practice}', practice.name),
            'is_open': is_open,
            'after_hours_message': after_hours_msg,
            'quick_replies': QUICK_REPLIES_MAP['INITIAL'],
        })
