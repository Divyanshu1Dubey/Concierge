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
from .services import create_email_record, get_or_create_thread, send_practice_email, send_appointment_email
from apps.practices.models import Practice


class EmailThreadListView(generics.ListCreateAPIView):
    """List or create email threads."""
    queryset = EmailThread.objects.all()
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['status']

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(
                Q(patient_email__icontains=search) |
                Q(subject__icontains=search)
            )
        return qs


class EmailThreadDetailView(generics.RetrieveUpdateAPIView):
    """Get or update an email thread."""
    queryset = EmailThread.objects.all()
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'


class EmailListView(generics.ListAPIView):
    """List emails, optionally filtered by thread, direction, or search."""
    serializer_class = EmailSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Email.objects.all().order_by('-created_at')
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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        to_email = request.data.get('to_email', '').strip()
        subject = request.data.get('subject', '').strip()
        body = request.data.get('body', '').strip()

        if not to_email:
            return Response({'error': 'Recipient email (to_email) is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not subject:
            return Response({'error': 'Email subject is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not body:
            return Response({'error': 'Email body is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve practice
        practice = request.user.practice
        if not practice:
            practice = Practice.objects.filter(active=True).first()

        send_result = send_practice_email(
            practice=practice,
            to_email=to_email,
            subject=subject,
            body=body,
            body_html=request.data.get('body_html'),
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
    queryset = EmailCadence.objects.all()
    serializer_class = EmailCadenceSerializer
    permission_classes = [permissions.IsAuthenticated]


class EmailCadenceDetailView(generics.RetrieveUpdateAPIView):
    """Get or update an email cadence."""
    queryset = EmailCadence.objects.all()
    serializer_class = EmailCadenceSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
