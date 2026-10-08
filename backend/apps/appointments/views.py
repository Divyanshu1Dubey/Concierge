"""Views for Appointments, Front-Desk Command Center, and AI Workspace."""
import logging
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone

from .models import Appointment, AppointmentSlot, Service
from .serializers import (
    AppointmentSerializer, AppointmentSlotSerializer, ServiceSerializer,
    AIDraftRequestSerializer, SendReplySerializer
)
from apps.core.permissions import TenantIsolationMixin, IsTenantViewer, IsTenantMember
from apps.practices.models import Practice, EmailTemplate

logger = logging.getLogger(__name__)


class ServiceListView(TenantIsolationMixin, generics.ListAPIView):
    """List available services for the current tenant practice."""
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer
    permission_classes = [permissions.AllowAny]


class AvailableSlotsView(generics.ListAPIView):
    """List available appointment slots."""
    serializer_class = AppointmentSlotSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        practice_id = self.request.query_params.get('practice_id')
        service_id = self.request.query_params.get('service_id')

        queryset = AppointmentSlot.objects.filter(
            is_available=True,
            start_time__gte=timezone.now(),
        )
        if practice_id:
            queryset = queryset.filter(service__practice_id=practice_id)
        if service_id:
            queryset = queryset.filter(service_id=service_id)

        return queryset.order_by('start_time')


class AppointmentListCreateView(TenantIsolationMixin, generics.ListCreateAPIView):
    """List requests/appointments for the authenticated tenant practice."""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        intent_filter = self.request.query_params.get('intent')
        if intent_filter:
            qs = qs.filter(intent=intent_filter)

        urgency_filter = self.request.query_params.get('urgency')
        if urgency_filter:
            qs = qs.filter(urgency=urgency_filter)

        priority_filter = self.request.query_params.get('priority')
        if priority_filter:
            qs = qs.filter(priority=priority_filter)

        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient_email__icontains=search) |
                Q(patient_name__icontains=search) |
                Q(patient_phone__icontains=search) |
                Q(service_name__icontains=search) |
                Q(confirmation_code__icontains=search)
            )
        return qs.order_by('-created_at')

    def perform_create(self, serializer):
        user = self.request.user
        practice = user.practice if user and user.is_authenticated else None
        serializer.save(practice=practice)


class AppointmentDetailView(generics.RetrieveUpdateAPIView):
    """Get or update an appointment request."""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]
    lookup_field = 'id'

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.practice:
            return Appointment.objects.filter(practice=user.practice)
        return Appointment.objects.none()


class AppointmentStatsView(APIView):
    """Summary counts for the Front Desk inbox tabs."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = request.user.practice
        if not practice:
            return Response({'total': 0, 'pending': 0, 'emergency': 0, 'contacted': 0})

        qs = Appointment.objects.filter(practice=practice)
        return Response({
            'total': qs.count(),
            'pending': qs.filter(status='pending').count(),
            'emergency': qs.filter(Q(urgency='URGENT') | Q(intent='emergency')).count(),
            'appointment': qs.filter(intent__in=['new_patient', 'cleaning', 'appointment']).count(),
            'question': qs.filter(intent='question').count(),
            'reschedule': qs.filter(intent='reschedule').count(),
            'cancel': qs.filter(intent='cancel').count(),
            'handoff': qs.filter(intent='handoff').count(),
            'contacted': qs.filter(status='contacted').count(),
            'confirmed': qs.filter(status='confirmed').count(),
        })


class AIDraftView(APIView):
    """AI Assistant inside the Front Desk workspace: draft, refine, translate, summarize."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(Appointment, id=id, practice=request.user.practice)
        serializer = AIDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        current_text = serializer.validated_data.get('current_text', '')
        target_lang = serializer.validated_data.get('target_language', 'Spanish')

        practice = request.user.practice
        practice_name = practice.name if practice else "Our Practice"

        # 1. Base template rendering
        tpl = EmailTemplate.objects.filter(practice=practice, template_type=appt.intent).first()
        context_vars = {
            'patient_name': appt.patient_name or 'there',
            'phone': practice.phone if practice else '',
            'email': appt.patient_email or '',
            'service': appt.service_name or (appt.service.name if appt.service else 'Appointment'),
            'intent': appt.intent,
            'preferred_date': appt.preferred_date or 'Flexible',
            'preferred_time': appt.preferred_time or 'Flexible',
            'message': appt.message or '',
            'practice': practice_name,
        }

        default_base_draft = (
            f"Hi {appt.patient_name or 'there'},\n\n"
            f"Thanks for reaching out! We would be delighted to help with your {appt.service_name or appt.intent or 'appointment'}.\n\n"
            f"We received your request for:\n"
            f"• Preferred Date: {appt.preferred_date or 'Flexible'}\n"
            f"• Preferred Time: {appt.preferred_time or 'Flexible'}\n\n"
            f"Please let us know what time works best for you and our front desk will coordinate the visit.\n\n"
            f"Best regards,\n"
            f"{practice_name} Front Desk"
        )

        base_draft = current_text if current_text else (tpl.render(context_vars)[1] if tpl else default_base_draft)

        # 2. AI Enhancement
        from apps.ai_service.engine import AIEngine
        try:
            ai_engine = AIEngine()
        except Exception:
            ai_engine = None

        if not ai_engine or not getattr(ai_engine, 'provider', None):
            return Response({'action': action, 'result': base_draft, 'draft': base_draft})

        try:
            if action == 'draft':
                prompt = (
                    f"You are a front desk coordinator at {practice_name}. Write a friendly, professional 3-paragraph reply to this patient request:\n"
                    f"Patient: {appt.patient_name}, Request: {appt.service_name or appt.intent}, Date: {appt.preferred_date}, Time: {appt.preferred_time}, Note: {appt.message}.\n"
                    f"Never claim the appointment is already booked; invite them to confirm suitable timing."
                )
                res = ai_engine.chat(prompt)
                content = res.get('content', '')
                if not content or "trouble connecting" in content.lower():
                    content = base_draft
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'professional':
                prompt = f"Rewrite this dental front desk message to be more formal and professional:\n\n{base_draft}"
                res = ai_engine.chat(prompt)
                content = res.get('content', '')
                if not content or "trouble connecting" in content.lower():
                    content = base_draft
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'shorter':
                prompt = f"Condense this dental front desk reply into 2-3 friendly, concise sentences:\n\n{base_draft}"
                res = ai_engine.chat(prompt)
                content = res.get('content', '')
                if not content or "trouble connecting" in content.lower():
                    content = base_draft
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'warmer':
                prompt = f"Rewrite this dental front desk reply to sound exceptionally warm, welcoming, and empathetic:\n\n{base_draft}"
                res = ai_engine.chat(prompt)
                content = res.get('content', '')
                if not content or "trouble connecting" in content.lower():
                    content = base_draft
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'translate':
                prompt = f"Translate the following email message into {target_lang}. Preserve professional tone:\n\n{base_draft}"
                res = ai_engine.chat(prompt)
                content = res.get('content', base_draft)
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'summarize':
                sum_text = appt.ai_summary or f"Patient requested {appt.intent} for {appt.preferred_date} ({appt.preferred_time})."
                return Response({
                    'action': action,
                    'result': sum_text,
                    'draft': sum_text
                })

            elif action == 'explain':
                prompt = f"Explain what the front desk should know about this patient request in 2 sentences:\nService: {appt.service_name}, Urgency: {appt.urgency}, Patient message: {appt.message}"
                res = ai_engine.chat(prompt)
                content = res.get('content', 'Standard routine patient inquiry.')
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'next_action':
                if appt.urgency == 'URGENT' or appt.intent == 'emergency':
                    msg = 'Call patient immediately via phone to offer immediate same-day chair.'
                else:
                    msg = 'Send proposed appointment opening and request confirmation.'
                return Response({'action': action, 'result': msg, 'draft': msg})

        except Exception as e:
            logger.warning(f"AI draft failure: {e}")
            return Response({'action': action, 'result': base_draft, 'draft': base_draft})


class SaveDraftView(APIView):
    """Save response draft on request."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(Appointment, id=id, practice=request.user.practice)
        draft_text = request.data.get('draft', '')
        appt.response_draft = draft_text
        appt.save(update_fields=['response_draft'])
        return Response({'status': 'saved', 'draft': draft_text})


class SendReplyView(APIView):
    """Send front-desk reply email and update request status."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(Appointment, id=id, practice=request.user.practice)
        serializer = SendReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        practice = request.user.practice

        # Send via email service
        from apps.emails.services import send_practice_email
        send_result = send_practice_email(
            practice=practice,
            to_email=data['to_email'],
            subject=data['subject'],
            body=data['body'],
            reply_to=data.get('reply_to'),
            appointment=appt
        )

        if not send_result.get('success'):
            return Response({
                'status': 'failed',
                'delivery': send_result,
                'message': f"Failed to send email: {send_result.get('error', 'Delivery failed')}"
            }, status=status.HTTP_400_BAD_REQUEST)

        appt.status = 'contacted'
        appt.response_draft = data['body']
        appt.response_sent_at = timezone.now()
        appt.save(update_fields=['status', 'response_draft', 'response_sent_at'])

        msg = f"Reply sent successfully to {data['to_email']}!"
        if send_result.get('warning'):
            msg = f"Reply recorded! ({send_result['warning']})"

        return Response({
            'status': 'sent',
            'delivery': send_result,
            'message': msg,
        })


class AddInternalNoteView(APIView):
    """Add staff internal note to request."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(Appointment, id=id, practice=request.user.practice)
        note_text = request.data.get('text', '').strip()
        if not note_text:
            return Response({'error': 'Note text cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)

        notes = list(appt.internal_notes or [])
        notes.append({
            'author': request.user.full_name or request.user.email,
            'text': note_text,
            'created_at': timezone.now().isoformat(),
        })
        appt.internal_notes = notes
        appt.save(update_fields=['internal_notes'])
        return Response({'status': 'added', 'notes': notes})


class UpdateRequestStatusView(APIView):
    """Update status, priority, or staff assignment."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(Appointment, id=id, practice=request.user.practice)
        new_status = request.data.get('status')
        new_priority = request.data.get('priority')
        assigned_to_id = request.data.get('assigned_to')

        if new_status:
            appt.status = new_status
            if new_status == 'confirmed' and not appt.confirmed_at:
                appt.confirmed_at = timezone.now()
        if new_priority:
            appt.priority = new_priority
            appt.urgency = new_priority
        if assigned_to_id:
            from apps.users.models import User
            staff = User.objects.filter(id=assigned_to_id, practice=request.user.practice).first()
            if staff:
                appt.assigned_to = staff

        appt.save()
        return Response({'status': appt.status, 'priority': appt.priority, 'assigned_to': str(appt.assigned_to.id) if appt.assigned_to else None})
