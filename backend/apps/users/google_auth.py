"""
"Sign in with Google" for existing staff accounts.

Flow: the login page sends the browser to /api/auth/google/login/ (django-allauth). Google returns to
/api/auth/google/login/callback/. The adapter below only lets the login through when Google reports a
verified email that matches an existing, active HeyJarvis user whose practice is not suspended; nobody can
create an account this way. allauth then redirects to /api/auth/google/complete/, which turns the short-lived
Django session into a one-time code and sends the browser back to the login page (code in the URL fragment,
so it never reaches server logs). The page exchanges the code at /api/auth/google/exchange/ for the same JWT
pair a password login returns. The code is valid for 2 minutes and only once.
"""
import logging

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.contrib.auth import logout
from django.core import signing
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.views import View
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)
CODE_SALT = 'users.google-login'
CODE_MAX_AGE = 120


def google_enabled() -> bool:
    return bool(getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '') and getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', ''))


def _login_page(params: str = '', fragment: str = '') -> str:
    base = (getattr(settings, 'FRONTEND_URL', '') or '').rstrip('/')
    return f"{base}/login" + (f"?{params}" if params else '') + (f"#{fragment}" if fragment else '')


def _refuse(reason: str):
    raise ImmediateHttpResponse(HttpResponseRedirect(_login_page(f'google={reason}')))


class StaffOnlyGoogleAdapter(DefaultSocialAccountAdapter):
    """Google can sign in existing staff only. Accounts are never created from a Google login."""

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        from apps.users.authentication import practice_suspended
        from apps.users.models import User
        data = sociallogin.account.extra_data or {}
        email = (data.get('email') or (sociallogin.user.email if sociallogin.user else '') or '').strip().lower()
        if not email or data.get('email_verified') is False:
            _refuse('unverified')
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            _refuse('no_account')
        if not user.is_active:
            _refuse('disabled')
        if practice_suspended(user):
            _refuse('suspended')
        if sociallogin.is_existing:
            if sociallogin.user.pk != user.pk:  # Google account linked to a different user than its email
                _refuse('no_account')
            return
        # First Google sign-in for this staff member: link the Google identity to their account.
        sociallogin.connect(request, user)
        if not user.google_id:
            user.google_id = str(data.get('sub') or sociallogin.account.uid)[:255]
            user.save(update_fields=['google_id'])

    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        logger.info("Google sign-in failed: %s", type(exception).__name__ if exception else error)
        raise ImmediateHttpResponse(HttpResponseRedirect(_login_page('google=failed')))


def _code_for(user) -> str:
    stamp = user.last_login.isoformat() if user.last_login else ''
    return signing.dumps({'u': str(user.pk), 'l': stamp}, salt=CODE_SALT)


class GoogleCompleteView(View):
    """allauth lands here after a successful Google login; hand a one-time code to the SPA."""

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        if user is None:
            return HttpResponseRedirect(_login_page('google=failed'))
        code = _code_for(user)
        logout(request)  # the dashboard uses JWTs; do not keep a cookie session around
        return HttpResponseRedirect(_login_page(fragment=f'google_code={code}'))


class GoogleExchangeView(APIView):
    """Exchange the one-time code for the normal JWT pair."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def post(self, request):
        from apps.users.authentication import SUSPENDED_MESSAGE, practice_suspended
        from apps.users.models import User
        from apps.users.serializers import UserSerializer
        bad = Response({'error': 'This Google sign-in link has expired. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            data = signing.loads(str(request.data.get('code') or ''), salt=CODE_SALT, max_age=CODE_MAX_AGE)
        except signing.BadSignature:
            return bad
        user = User.objects.filter(pk=data.get('u')).first()
        if user is None or not user.is_active:
            return bad
        stamp = user.last_login.isoformat() if user.last_login else ''
        if stamp != data.get('l'):
            return bad  # already used (last_login moved on) or superseded by a newer login
        if practice_suspended(user):
            return Response({'error': SUSPENDED_MESSAGE}, status=status.HTTP_403_FORBIDDEN)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        refresh = RefreshToken.for_user(user)
        return Response({'access': str(refresh.access_token), 'refresh': str(refresh), 'user': UserSerializer(user).data})
