from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import NotificationQueue


def queue_notifications_for_event(event):
    """
    Recalculates and schedules pending reminders for a given calendar event.
    
    1. Cancels any existing pending reminders for this event.
    2. Calculates target reminder times (start_time - interval).
    3. Queues new pending reminder rows for any target time still in the future.
    """
    # Read global reminder defaults from settings (or fall back to defaults)
    intervals = getattr(settings, "NOTIFICATION_DEFAULT_INTERVALS_MINUTES", [60])
    methods = getattr(settings, "NOTIFICATION_DEFAULT_METHODS", ["email"])

    # If the user model defines custom reminder preferences, prioritize them
    user = event.user
    if hasattr(user, "notification_intervals") and getattr(user, "notification_intervals"):
        intervals = getattr(user, "notification_intervals")
    if hasattr(user, "notification_methods") and getattr(user, "notification_methods"):
        methods = getattr(user, "notification_methods")

    created_rows = []
    now = timezone.now()

    with transaction.atomic():
        # a) Cancel all currently pending reminders for this event
        # (Leave already sent, failed, or processing rows untouched)
        NotificationQueue.objects.filter(
            event=event,
            status=NotificationQueue.Status.PENDING,
        ).update(status=NotificationQueue.Status.CANCELED)

        # b) Calculate target delivery times for each interval and delivery method
        for interval in intervals:
            target_time = event.start_time - timedelta(minutes=interval)

            # c) Skip reminders whose send time has already passed
            if target_time <= now:
                continue

            for method in methods:
                notification = NotificationQueue.objects.create(
                    event=event,
                    user=user,
                    target_time=target_time,
                    delivery_method=method,
                    status=NotificationQueue.Status.PENDING,
                )
                created_rows.append(notification)

    return created_rows
