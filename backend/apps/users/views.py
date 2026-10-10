"""
User views and permissions.
"""
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework.throttling import ScopedRateThrottle
from django.conf import settings
from apps.core.permissions import IsAgencyAdmin
from .models import User
from .serializers import (
    UserSerializer, UserCreateSerializer, LoginSerializer,
    TokenResponseSerializer, ChangePasswordSerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    Self-service registration. Disabled unless ALLOW_PUBLIC_REGISTRATION is set:
    staff accounts are provisioned by agency or practice administrators.
    """
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def create(self, request, *args, **kwargs):
        if not getattr(settings, 'ALLOW_PUBLIC_REGISTRATION', False):
            return Response(
                {'detail': 'Self-service registration is disabled. Ask your practice administrator for an account.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)


class LoginView(TokenObtainPairView):
    """Login endpoint - returns JWT tokens."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']

        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(user).data,
        })


class LogoutView(generics.GenericAPIView):
    """Logout - blacklist the refresh token."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'error': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            if str(token.get('user_id')) != str(request.user.id):
                return Response({'error': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)
            token.blacklist()
        except TokenError:
            return Response({'error': 'Invalid or expired token.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """Get or update the current user."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    """Secure endpoint for authenticated users to update their password."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'old_password': ['Current password is incorrect.']},
                status=status.HTTP_400_BAD_REQUEST
            )
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({'message': 'Password updated successfully.'}, status=status.HTTP_200_OK)


class SeedUsersView(generics.GenericAPIView):
    """Seed / verify baseline demo accounts (agency admins only, demo mode only)."""
    permission_classes = [permissions.IsAuthenticated, IsAgencyAdmin]

    def post(self, request):
        from .seed_data import seed_all_demo_data, demo_accounts_enabled
        if not demo_accounts_enabled():
            return Response({'error': 'Demo accounts are disabled in this environment.'}, status=status.HTTP_403_FORBIDDEN)
        accounts = seed_all_demo_data()
        # Sanitize output: never return plain text passwords over API
        sanitized = [{'email': a.get('email'), 'role': a.get('role')} for a in accounts]
        return Response({
            'status': 'success',
            'message': 'Baseline practices and accounts verified successfully.',
            'accounts': sanitized,
        }, status=status.HTTP_200_OK)


class AuthConfigView(generics.GenericAPIView):
    """Public, non-sensitive auth configuration consumed by the login page."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        # Never expose demo accounts or credentials here: this endpoint is public.
        return Response({
            'registration_enabled': bool(getattr(settings, 'ALLOW_PUBLIC_REGISTRATION', False)),
            'access_requests_enabled': True,
        })


class PasswordResetRequestView(generics.GenericAPIView):
    """Email a reset link. Always answers the same way so accounts cannot be enumerated."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        from .account_emails import send_set_password_email
        from .authentication import practice_suspended
        email = str(request.data.get('email', '')).strip().lower()
        if email:
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user and not practice_suspended(user):
                send_set_password_email(user, request, invite=False)
        return Response({'message': 'If an account exists for that email, a reset link has been sent.'})


class PasswordResetConfirmView(generics.GenericAPIView):
    """Set a new password from an emailed (invite or reset) link."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'auth'

    def post(self, request):
        from django.contrib.auth.password_validation import validate_password
        from django.contrib.auth.tokens import default_token_generator
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.utils.encoding import force_str
        from django.utils.http import urlsafe_base64_decode

        uid = str(request.data.get('uid', ''))
        token = str(request.data.get('token', ''))
        new_password = str(request.data.get('new_password', '') or '')
        confirm = str(request.data.get('new_password_confirm', '') or '')
        invalid = Response({'error': 'This link is invalid or has expired. Request a new one.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.filter(pk=force_str(urlsafe_base64_decode(uid)), is_active=True).first()
        except (TypeError, ValueError, OverflowError, DjangoValidationError):
            user = None
        if not user or not default_token_generator.check_token(user, token):
            return invalid
        if new_password != confirm:
            return Response({'error': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({'error': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        # Sign out every existing session for this account.
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
            for outstanding in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except Exception:
            pass
        return Response({'message': 'Your password has been set. You can now sign in.'})
