"""
Views for the emails app.
"""
from rest_framework import generics, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Q
from django.utils import timezone
from .models import EmailThread, Email, EmailCadence
from .serializers import EmailThreadSerializer, EmailSerializer, EmailCadenceSerializer
from .services import send_practice_email
from apps.core.permissions import IsTenantMember, get_request_practice
from rest_framework.exceptions import ValidationError


def _scoped(request, model):
    practice = get_request_practice(request)
    if not practice:
        return model.objects.none()
    return model.objects.filter(practice=practice)


class EmailThreadListView(generics.ListCreateAPIView):
    """List or create email threads."""
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    filterset_fields = ['status']

    def perform_create(self, serializer):
        practice = get_request_practice(self.request)
        if not practice:
            raise ValidationError({'practice': ['No practice selected.']})
        serializer.save(practice=practice)

    def get_queryset(self):
        qs = _scoped(self.request, EmailThread).prefetch_related('emails')
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient_email__icontains=search) |
                Q(subject__icontains=search)
            )
        return qs


class EmailThreadDetailView(generics.RetrieveUpdateAPIView):
    """Get or update an email thread."""
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    lookup_field = 'id'

    def get_queryset(self):
        return _scoped(self.request, EmailThread)


class EmailListView(generics.ListAPIView):
    """List emails, optionally filtered by thread, direction, or search."""
    serializer_class = EmailSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        practice = get_request_practice(self.request)
        if not practice:
            return Email.objects.none()
        qs = Email.objects.filter(thread__practice=practice).order_by('-created_at')
        thread_id = self.request.query_params.get('thread_id') or self.request.query_params.get('thread')
        if thread_id:
            qs = qs.filter(thread_id=thread_id)
        direction = self.request.query_params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(to_email__icontains=search) |
                Q(from_email__icontains=search) |
                Q(subject__icontains=search) |
                Q(body__icontains=search)
            )
        return qs


class EmailSendView(APIView):
    """Send an outbound email to a patient with thread management and status tracking."""
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def post(self, request):
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        to_email = str(request.data.get('to_email', '') or '').strip()
        subject = str(request.data.get('subject', '') or '').strip()[:500]
        body = str(request.data.get('body', '') or '').strip()

        if not to_email:
            return Response({'error': 'Recipient email (to_email) is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not subject:
            return Response({'error': 'Email subject is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not body:
            return Response({'error': 'Email body is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_email(to_email)
        except DjangoValidationError:
            return Response({'error': 'Enter a valid recipient email address.'}, status=status.HTTP_400_BAD_REQUEST)

        practice = get_request_practice(request)
        if not practice:
            return Response({'error': 'No practice selected for sending.'}, status=status.HTTP_400_BAD_REQUEST)

        send_result = send_practice_email(
            practice=practice,
            to_email=to_email,
            subject=subject,
            body=body,
            body_html=None,
            reply_to=request.data.get('reply_to'),
        )

        msg = f"Email sent successfully to {to_email}"
        if send_result.get('warning'):
            msg = f"Email recorded! ({send_result['warning']})"

        if not send_result.get('success'):
            return Response({
                'status': 'failed',
                'delivery': send_result,
                'message': f"Delivery notice: {send_result.get('error', 'Failed to dispatch email')}",
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'status': 'sent',
            'delivery': send_result,
            'message': msg,
        }, status=status.HTTP_201_CREATED)


class EmailCadenceListView(generics.ListCreateAPIView):
    """List or create email cadences."""
    serializer_class = EmailCadenceSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]

    def get_queryset(self):
        return _scoped(self.request, EmailCadence)

    def perform_create(self, serializer):
        practice = get_request_practice(self.request)
        if not practice:
            raise ValidationError({'practice': ['No practice selected.']})
        serializer.save(practice=practice)


class EmailCadenceDetailView(generics.RetrieveUpdateAPIView):
    """Get or update an email cadence."""
    serializer_class = EmailCadenceSerializer
    permission_classes = [permissions.IsAuthenticated, IsTenantMember]
    lookup_field = 'id'

    def get_queryset(self):
        return _scoped(self.request, EmailCadence)
