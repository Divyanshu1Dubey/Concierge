"""Keep the recall list current when the front desk marks a request completed."""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender='appointments.Appointment')
def appointment_completed(sender, instance, **kwargs):
    if instance.status != 'completed' or not instance.practice_id:
        return
    try:
        from .outreach import record_completed_visit
        record_completed_visit(instance)
    except Exception as exc:  # never break saving a request
        logger.warning("Recall update failed for appointment %s: %s", instance.id, type(exc).__name__)



def _invalidate_queue(practice_id):
    """Anything that can change who is waiting makes the next Follow-ups page load rescan immediately."""
    if practice_id:
        from django.core.cache import cache
        cache.delete(f'growth-scan-{practice_id}')


@receiver(post_save, sender='appointments.Appointment')
def appointment_changed(sender, instance, **kwargs):
    _invalidate_queue(instance.practice_id)


@receiver(post_save, sender='appointments.AppointmentOffer')
def offer_changed(sender, instance, **kwargs):
    _invalidate_queue(instance.practice_id)


@receiver(post_save, sender='emails.Email')
def email_changed(sender, instance, **kwargs):
    if instance.direction == 'incoming':
        _invalidate_queue(getattr(instance.thread, 'practice_id', None))


@receiver(post_save, sender='growth.SmsMessage')
def sms_changed(sender, instance, **kwargs):
    if instance.direction == 'in':
        _invalidate_queue(instance.practice_id)
