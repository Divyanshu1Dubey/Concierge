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
from rest_framework.exceptions import ValidationError
from apps.core.permissions import TenantIsolationMixin, IsTenantViewer, IsTenantMember, get_request_practice
from apps.practices.models import Practice, EmailTemplate

logger = logging.getLogger(__name__)

VALID_STATUSES = {choice for choice, _ in Appointment.STATUS_CHOICES}
VALID_PRIORITIES = {choice for choice, _ in Appointment.PRIORITY_CHOICES}


def scoped_appointments(request):
    """Appointments visible to the requesting staff member (tenant-scoped)."""
    practice = get_request_practice(request)
    if not practice:
        return Appointment.objects.none()
    return Appointment.objects.filter(practice=practice)


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
        # Inbox tabs use the same definitions as AppointmentStatsView so counts match lists.
        tab = self.request.query_params.get('tab')
        if tab == 'new':
            qs = qs.filter(status='pending')
        elif tab == 'emergency':
            qs = qs.filter(Q(urgency='URGENT') | Q(intent='emergency'))
        elif tab == 'appointment':
            qs = qs.filter(intent__in=['new_patient', 'cleaning', 'appointment'])
        elif tab in ('question', 'reschedule', 'cancel', 'handoff'):
            qs = qs.filter(intent=tab)
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['practice'] = get_request_practice(self.request)
        return context

    def perform_create(self, serializer):
        practice = get_request_practice(self.request)
        if not practice:
            raise ValidationError({'practice': ['Select a practice before creating a request.']})
        serializer.save(practice=practice)


class AppointmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Get or update an appointment request."""
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]
    lookup_field = 'id'

    def get_queryset(self):
        return scoped_appointments(self.request)

    def perform_update(self, serializer):
        new_status = serializer.validated_data.get('status')
        instance = serializer.instance
        extra = {}
        if new_status == Appointment.STATUS_CONFIRMED and not instance.confirmed_at:
            extra['confirmed_at'] = timezone.now()
        if new_status == Appointment.STATUS_CANCELLED and not instance.cancelled_at:
            extra['cancelled_at'] = timezone.now()
        serializer.save(**extra)

    def destroy(self, request, *args, **kwargs):
        """Permanently delete a patient request (e.g. a data-deletion request). Practice admins only."""
        from apps.core.permissions import is_practice_admin_user
        from apps.practices.models import AuditLog
        if not is_practice_admin_user(request.user):
            return Response({'error': 'Practice administrator permissions required.'}, status=status.HTTP_403_FORBIDDEN)
        appt = self.get_object()
        with_conversation = str(request.query_params.get('delete_conversation', '')).lower() in ('1', 'true', 'yes')
        practice, code = appt.practice, appt.confirmation_code
        conversation = appt.conversation if with_conversation else None
        appt.delete()
        if conversation is not None:
            conversation.delete()
        AuditLog.objects.create(
            practice=practice, actor=request.user, action='PATIENT_REQUEST_DELETED',
            details={'reference': code, 'conversation_deleted': conversation is not None},
            ip_address=request.META.get('REMOTE_ADDR'),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AppointmentStatsView(APIView):
    """Summary counts for the Front Desk inbox tabs."""
    permission_classes = [permissions.IsAuthenticated, IsTenantViewer]

    def get(self, request):
        practice = get_request_practice(request)
        if not practice:
            return Response({
                'total': 0, 'pending': 0, 'emergency': 0, 'appointment': 0, 'question': 0,
                'reschedule': 0, 'cancel': 0, 'handoff': 0, 'contacted': 0, 'confirmed': 0,
            })

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
        appt = get_object_or_404(scoped_appointments(request), id=id)
        serializer = AIDraftRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        current_text = serializer.validated_data.get('current_text', '')
        target_lang = serializer.validated_data.get('target_language', 'Spanish')

        practice = appt.practice
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

        if not ai_engine or not getattr(ai_engine, 'available', False):
            # Tell the UI so staff know the text is the unchanged template, not an AI result.
            return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})

        try:
            if action == 'draft':
                prompt = (
                    f"You are a front desk coordinator at {practice_name}. Write a friendly, professional 3-paragraph reply to this patient request:\n"
                    f"Patient: {appt.patient_name}, Request: {appt.service_name or appt.intent}, Date: {appt.preferred_date}, Time: {appt.preferred_time}, Note: {appt.message}.\n"
                    f"Never claim the appointment is already booked; invite them to confirm suitable timing."
                )
                latest_reply = _latest_patient_reply(appt)
                if latest_reply:
                    prompt += (
                        "\n\nThe patient has since replied by email. Answer this latest message directly "
                        "(using only facts you were given):\n" + latest_reply[:3000]
                    )
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content') or ''
                if not content or "trouble connecting" in content.lower():
                    return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'professional':
                prompt = f"Rewrite this dental front desk message to be more formal and professional:\n\n{base_draft}"
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content') or ''
                if not content or "trouble connecting" in content.lower():
                    return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'shorter':
                prompt = f"Condense this dental front desk reply into 2-3 friendly, concise sentences:\n\n{base_draft}"
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content') or ''
                if not content or "trouble connecting" in content.lower():
                    return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'warmer':
                prompt = f"Rewrite this dental front desk reply to sound exceptionally warm, welcoming, and empathetic:\n\n{base_draft}"
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content') or ''
                if not content or "trouble connecting" in content.lower():
                    return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'translate':
                prompt = f"Translate the following email message into {target_lang}. Preserve professional tone:\n\n{base_draft}"
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content')
                if not content:
                    return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
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
                res = ai_engine.chat(prompt, practice=practice, audience='staff')
                content = res.get('content') or 'Standard routine patient inquiry.'
                return Response({'action': action, 'result': content, 'draft': content})

            elif action == 'next_action':
                if appt.urgency == 'URGENT' or appt.intent == 'emergency':
                    msg = 'Call patient immediately via phone to offer immediate same-day chair.'
                else:
                    msg = 'Send proposed appointment opening and request confirmation.'
                return Response({'action': action, 'result': msg, 'draft': msg})

        except Exception as e:
            logger.warning("AI draft failure: %s", type(e).__name__)
            return Response({'action': action, 'result': base_draft, 'draft': base_draft, 'ai_unavailable': True})
        return Response({'action': action, 'result': base_draft, 'draft': base_draft})


class SaveDraftView(APIView):
    """Save response draft on request."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(scoped_appointments(request), id=id)
        draft_text = str(request.data.get('draft', '') or '')[:20000]
        appt.response_draft = draft_text
        update_fields = ['response_draft']
        offered_time = str(request.data.get('offered_time') or '').strip()[:100]
        if offered_time:
            appt.preferred_time = offered_time
            update_fields.append('preferred_time')
        appt.save(update_fields=update_fields)
        return Response({'status': 'saved', 'draft': draft_text, 'preferred_time': appt.preferred_time})


class SendReplyView(APIView):
    """Send front-desk reply email and update request status."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(scoped_appointments(request), id=id)
        serializer = SendReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        practice = appt.practice

        # Send via email service, continuing this request's thread (and answering the
        # patient's latest reply, if any) so the conversation stays together.
        from apps.emails.services import send_practice_email
        from apps.emails.models import Email, EmailThread
        thread = (EmailThread.objects.filter(practice=practice, metadata__appointment_id=str(appt.id))
                  .order_by('-last_message_at').first())
        last_reply = (Email.objects.filter(thread=thread, direction=Email.DIRECTION_INCOMING)
                      .exclude(provider_message_id='').order_by('-created_at').first()) if thread else None

        # Optional: ask the patient to confirm a specific date/time (branded email + response link).
        body_text, body_html, offer = data['body'], None, None
        if _truthy(request.data.get('request_confirmation')):
            offered_date, offered_time, error = _parse_offer(request, practice)
            if error:
                return Response({'status': 'failed', 'message': error}, status=status.HTTP_400_BAD_REQUEST)
            from .offers import create_offer, offer_link, render_offer_email
            offer, token = create_offer(appt, offered_date, offered_time, request.user)
            body_html, suffix = render_offer_email(appt, offered_date, offered_time, data['body'],
                                                   offer_link(request, token))
            body_text = data['body'].rstrip() + suffix

        send_result = send_practice_email(
            practice=practice,
            to_email=data['to_email'],
            subject=data['subject'],
            body=body_text,
            body_html=body_html,
            reply_to=data.get('reply_to'),
            appointment=appt,
            thread=thread,
            in_reply_to=last_reply.provider_message_id if last_reply else None,
        )

        if not send_result.get('success'):
            if offer is not None:
                offer.delete()  # the patient never received this link; earlier offers stay valid
            return Response({
                'status': 'failed',
                'delivery': send_result,
                'message': f"Failed to send email: {send_result.get('error', 'Delivery failed')}"
            }, status=status.HTTP_400_BAD_REQUEST)

        appt.status = 'contacted'
        appt.response_draft = data['body']
        appt.response_sent_at = timezone.now()
        update_fields = ['status', 'response_draft', 'response_sent_at']
        if offer is not None:
            from .offers import activate_offer
            activate_offer(offer)
            appt.confirmed_at = None  # a new time is awaiting the patient's confirmation
            update_fields.append('confirmed_at')
        offered_time = str(request.data.get('offered_time') or '').strip()[:100]
        if offered_time:
            appt.preferred_time = offered_time
            update_fields.append('preferred_time')
        appt.save(update_fields=update_fields)

        msg = f"Reply sent successfully to {data['to_email']}!"
        if send_result.get('warning'):
            msg = f"Reply recorded! ({send_result['warning']})"

        if offer is not None and not send_result.get('warning'):
            msg = f"Confirmation request sent to {data['to_email']}. You'll see their answer here."
        return Response({
            'status': 'sent',
            'delivery': send_result,
            'message': msg,
            'confirmation_requested': offer is not None,
        })


class AddInternalNoteView(APIView):
    """Add staff internal note to request."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(scoped_appointments(request), id=id)
        note_text = str(request.data.get('text', '') or '').strip()[:4000]
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
        appt = get_object_or_404(scoped_appointments(request), id=id)
        new_status = request.data.get('status')
        new_priority = request.data.get('priority')
        assigned_to_id = request.data.get('assigned_to')

        if new_status:
            new_status = str(new_status).lower()
            if new_status not in VALID_STATUSES:
                return Response({'error': f"Invalid status. Choose one of: {', '.join(sorted(VALID_STATUSES))}"}, status=status.HTTP_400_BAD_REQUEST)
            appt.status = new_status
            if new_status == Appointment.STATUS_CONFIRMED and not appt.confirmed_at:
                appt.confirmed_at = timezone.now()
            if new_status == Appointment.STATUS_CANCELLED and not appt.cancelled_at:
                appt.cancelled_at = timezone.now()
        if new_priority:
            new_priority = str(new_priority).upper()
            if new_priority not in VALID_PRIORITIES:
                return Response({'error': f"Invalid priority. Choose one of: {', '.join(sorted(VALID_PRIORITIES))}"}, status=status.HTTP_400_BAD_REQUEST)
            appt.priority = new_priority
            appt.urgency = new_priority
        if assigned_to_id:
            import uuid
            from apps.users.models import User
            try:
                uuid.UUID(str(assigned_to_id))
            except ValueError:
                return Response({'error': 'Invalid staff member id.'}, status=status.HTTP_400_BAD_REQUEST)
            staff = User.objects.filter(id=assigned_to_id, practice_id=appt.practice_id, is_active=True).first()
            if not staff:
                return Response({'error': 'Staff member not found in this practice.'}, status=status.HTTP_400_BAD_REQUEST)
            appt.assigned_to = staff

        appt.save()
        return Response({'status': appt.status, 'priority': appt.priority, 'assigned_to': str(appt.assigned_to.id) if appt.assigned_to else None})


def _latest_patient_reply(appt) -> str:
    """Text of the patient's most recent emailed reply on this request, if any."""
    from apps.emails.models import Email
    reply = (Email.objects.filter(thread__practice=appt.practice, thread__metadata__appointment_id=str(appt.id),
                                  direction=Email.DIRECTION_INCOMING)
             .order_by('-created_at').first())
    return reply.body if reply else ''


def _truthy(value) -> bool:
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _parse_offer(request, practice):
    """Validate the proposed date/time for a confirmation request. Returns (date, time, error)."""
    from datetime import date as _date
    from .offers import practice_tz
    raw_date = str(request.data.get('offered_date') or '').strip()
    offered_time = str(request.data.get('offered_time') or '').strip()
    try:
        offered_date = _date.fromisoformat(raw_date)
    except ValueError:
        return None, None, 'Choose the appointment date before asking the patient to confirm.'
    if not offered_time:
        return None, None, 'Choose the appointment time before asking the patient to confirm.'
    if len(offered_time) > 50:
        return None, None, 'The appointment time is too long.'
    today = timezone.now().astimezone(practice_tz(practice)).date()
    if offered_date < today:
        return None, None, 'The appointment date is in the past.'
    return offered_date, offered_time, None


class OfferPreviewView(APIView):
    """Render the exact branded email the patient will receive (no link is created)."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request, id):
        appt = get_object_or_404(scoped_appointments(request), id=id)
        offered_date, offered_time, error = _parse_offer(request, appt.practice)
        if error:
            return Response({'message': error}, status=status.HTTP_400_BAD_REQUEST)
        from .offers import render_offer_email
        html, _ = render_offer_email(appt, offered_date, offered_time, str(request.data.get('body') or ''),
                                     '#preview-only')
        return Response({'html': html})


class _PublicOfferMixin:
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get_offer(self, token):
        from .models import AppointmentOffer
        from .offers import hash_token
        if not token or len(token) > 100:
            return None
        return (AppointmentOffer.objects.select_related('appointment', 'practice', 'practice__settings')
                .filter(token_hash=hash_token(token)).first())


class PublicOfferView(_PublicOfferMixin, APIView):
    """Patient-facing: details of a confirmation request (read-only; never changes anything)."""
    from rest_framework.throttling import ScopedRateThrottle as _T
    throttle_classes = [_T]
    throttle_scope = 'widget'

    def get(self, request, token):
        from .offers import public_payload
        offer = self.get_offer(token)
        if offer is None or not offer.practice.active:
            return Response({'state': 'invalid', 'message': 'This link is not valid. Please contact the practice.'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(public_payload(offer))


class PublicOfferRespondView(_PublicOfferMixin, APIView):
    """Patient-facing: confirm, or ask for a different time."""
    from rest_framework.throttling import ScopedRateThrottle as _T
    throttle_classes = [_T]
    throttle_scope = 'widget_submit'
    action = ''

    def post(self, request, token):
        from .offers import OfferError, public_payload, respond
        offer = self.get_offer(token)
        if offer is None or not offer.practice.active:
            return Response({'state': 'invalid', 'message': 'This link is not valid. Please contact the practice.'},
                            status=status.HTTP_404_NOT_FOUND)
        try:
            offer, changed = respond(token, self.action, str(request.data.get('note') or ''))
        except OfferError as exc:
            return Response({**public_payload(offer), 'state': exc.state, 'message': exc.message},
                            status=status.HTTP_409_CONFLICT)
        return Response({**public_payload(offer), 'changed': changed})
