"""
Serializers for the users app.
"""
from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""
    full_name = serializers.ReadOnlyField()
    practice_name = serializers.SerializerMethodField()
    practice_slug = serializers.SerializerMethodField()
    normalized_role = serializers.ReadOnlyField()
    is_agency_admin = serializers.ReadOnlyField()
    is_practice_admin = serializers.ReadOnlyField()

    class Meta:
        model = User
        fields = [
            'id', 'email', 'first_name', 'last_name', 'full_name', 'phone',
            'role', 'normalized_role', 'is_agency_admin', 'is_practice_admin',
            'practice', 'practice_name', 'practice_slug',
            'avatar_url', 'is_verified', 'last_login', 'created_at',
        ]
        read_only_fields = ['id', 'last_login', 'created_at']

    def get_practice_name(self, obj):
        return obj.practice.name if obj.practice else ("HeyJarvis Platform" if obj.is_agency_admin else "No Practice Assigned")

    def get_practice_slug(self, obj):
        return obj.practice.slug if obj.practice else ""


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating users with role protection."""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone',
            'role', 'password', 'password_confirm',
        ]

    def validate_role(self, value):
        # Prevent privilege escalation through unauthenticated or non-admin registration
        request = self.context.get('request')
        is_authenticated_admin = bool(
            request and request.user and request.user.is_authenticated and
            (request.user.is_agency_admin or request.user.is_superuser)
        )
        if not is_authenticated_admin and value in ['AGENCY_ADMIN', 'ADMIN', 'OWNER']:
            raise serializers.ValidationError("Administrative roles can only be assigned by a platform administrator.")
        return value

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')
        
        request = self.context.get('request')
        is_authenticated_admin = bool(
            request and request.user and request.user.is_authenticated and
            (request.user.is_agency_admin or request.user.is_superuser)
        )
        if not is_authenticated_admin:
            role = validated_data.get('role', 'FRONT_DESK')
            if role in ['AGENCY_ADMIN', 'ADMIN', 'OWNER']:
                role = 'FRONT_DESK'
            validated_data['role'] = role
            validated_data['is_staff'] = False
            validated_data['is_superuser'] = False

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for login."""
    email = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        raw_email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''

        # 1. Standard Django authenticate by username (which is email)
        user = authenticate(username=raw_email, password=password)
        if not user:
            # 2. Try authenticate by email kwarg
            user = authenticate(email=raw_email, password=password)

        if not user:
            # 3. Direct DB lookup by case-insensitive email
            db_user = User.objects.filter(email__iexact=raw_email).first()
            if db_user and db_user.check_password(password):
                user = db_user

        if not user:
            raise serializers.ValidationError("Invalid email or password.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        data['user'] = user
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for authenticated password changes."""
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError("New passwords do not match.")
        return data


class TokenResponseSerializer(serializers.Serializer):
    """Serializer for JWT token response."""
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth token."""
    token = serializers.CharField()
