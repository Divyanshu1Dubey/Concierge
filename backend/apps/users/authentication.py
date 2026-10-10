"""JWT authentication that also enforces practice suspension."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

SUSPENDED_MESSAGE = 'Your practice account is suspended. Please contact your HeyJarvis administrator.'


def practice_suspended(user) -> bool:
    """Practice staff lose access while their practice is deactivated (agency admins never do)."""
    if not user or user.is_superuser or (user.role or '').upper() == 'AGENCY_ADMIN':
        return False
    practice = getattr(user, 'practice', None)
    return practice is not None and not practice.active


class ActivePracticeJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if practice_suspended(user):
            # Explicit body so clients can tell suspension apart from an expired session.
            raise AuthenticationFailed({'detail': SUSPENDED_MESSAGE, 'code': 'practice_suspended'})
        return user
