"""Signals for the practices app."""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.decorators import method_decorator
from .models import Practice, BookingRules, PracticeSettings


@receiver(post_save, sender=Practice)
def create_practice_defaults(sender, instance, created, **kwargs):
    """Create default booking rules and settings when a practice is created."""
    if created:
        BookingRules.objects.create(practice=instance)
        PracticeSettings.objects.create(practice=instance)
