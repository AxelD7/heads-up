from django.db.models.signals import post_save
from django.dispatch import receiver
from events.models import Event

from .services import queue_notifications_for_event


@receiver(post_save, sender=Event)
def handle_event_post_save(sender, instance, created, raw, **kwargs):
    """
    Trigger that recalculates reminders whenever an event is created or edited.
    Skips processing during raw database operations such as loading fixtures.
    """
    if raw:
        return

    queue_notifications_for_event(instance)
