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
    """Serializer for creating users."""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone',
            'role', 'password', 'password_confirm',
        ]

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Passwords don't match.")
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(serializers.Serializer):
    """Serializer for login."""
    email = serializers.EmailField()
    password = serializers.CharField()

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        data['user'] = user
        return data


class TokenResponseSerializer(serializers.Serializer):
    """Serializer for JWT token response."""
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class GoogleAuthSerializer(serializers.Serializer):
    """Serializer for Google OAuth token."""
    token = serializers.CharField()
