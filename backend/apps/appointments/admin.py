"""
Admin registrations for appointments app.
"""
from django.contrib import admin
from apps.appointments.models import Service, AppointmentSlot, Appointment


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'duration_minutes', 'price', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']


@admin.register(AppointmentSlot)
class AppointmentSlotAdmin(admin.ModelAdmin):
    list_display = ['service', 'start_time', 'end_time', 'available_spots', 'is_available']
    list_filter = ['is_available', 'service']
    search_fields = ['service__name']


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ['patient_name', 'patient_email', 'service', 'status', 'confirmation_code', 'created_at']
    list_filter = ['status', 'service']
    search_fields = ['patient_email', 'patient_name', 'confirmation_code']
    readonly_fields = ['id', 'confirmation_code', 'created_at']
