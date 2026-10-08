"""
User views and permissions.
"""
from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from .models import User
from .serializers import (
    UserSerializer, UserCreateSerializer, LoginSerializer,
    TokenResponseSerializer,
)


class RegisterView(generics.CreateAPIView):
    """Register a new user."""
    queryset = User.objects.all()
    serializer_class = UserCreateSerializer
    permission_classes = [permissions.AllowAny]


class LoginView(TokenObtainPairView):
    """Login endpoint - returns JWT tokens."""
    permission_classes = [permissions.AllowAny]

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
        try:
            refresh_token = request.data.get('refresh')
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'message': 'Logged out successfully.'}, status=status.HTTP_200_OK)
        except Exception:
            return Response({'error': 'Invalid token.'}, status=status.HTTP_400_BAD_REQUEST)


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """Get or update the current user."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class SeedUsersView(generics.GenericAPIView):
    """Ensure all demo practices and user accounts exist."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from .seed_data import seed_all_demo_data
        accounts = seed_all_demo_data()
        return Response({
            'status': 'success',
            'message': 'Demo practices and users ensured successfully.',
            'accounts': accounts,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        return self.get(request)



