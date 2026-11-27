from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from events.models import Event

from .services import cancel_notifications_for_event, queue_notifications_for_event


@receiver(post_save, sender=Event)
def handle_event_post_save(sender, instance, created, raw, **kwargs):
    """
    Trigger that recalculates reminders whenever an event is created or edited.
    Skips processing during raw database operations such as loading fixtures.
    """
    if raw:
        return

    queue_notifications_for_event(instance)


@receiver(pre_delete, sender=Event)
def handle_event_pre_delete(sender, instance, **kwargs):
    """
    Mark pending reminders for an event as canceled before the event is deleted
    so no stale reminders can ever be dispatched.
    """
    cancel_notifications_for_event(instance)
