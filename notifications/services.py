from datetime import timedelta
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from .models import NotificationQueue

logger = logging.getLogger(__name__)


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


def send_due_notifications():
    """
    Queries pending reminders whose target time has arrived, dispatches email
    notifications using Django SMTP, and updates status (sent, retrying, failed).
    
    Implements the 3-attempt retry policy defined in SDD Section 4.4 and Figure 4.1.
    """
    now = timezone.now()

    # Query all pending email reminders due to be sent now or earlier
    due_notifications = NotificationQueue.objects.filter(
        status=NotificationQueue.Status.PENDING,
        delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
        target_time__lte=now,
    ).select_related("event", "user")

    results = {
        "total": due_notifications.count(),
        "sent": 0,
        "retrying": 0,
        "failed": 0,
    }

    for notification in due_notifications:
        event = notification.event
        user = notification.user

        # Atomic claim: mark processing and increment delivery attempts
        with transaction.atomic():
            notification.status = NotificationQueue.Status.PROCESSING
            notification.attempts += 1
            notification.save(update_fields=["status", "attempts"])

        # Format user-friendly email content
        location_line = f"Location: {event.location}\n" if event.location else ""
        description_block = f"\nDetails:\n{event.description}\n" if event.description else ""

        message_body = (
            f"Hi {user.username},\n\n"
            f"This is a Heads Up reminder for your upcoming event:\n\n"
            f"Event: {event.title}\n"
            f"Category: {event.get_category_display()}\n"
            f"Start Time: {event.start_time.strftime('%Y-%m-%d %I:%M %p UTC')}\n"
            f"End Time: {event.end_time.strftime('%Y-%m-%d %I:%M %p UTC')}\n"
            f"{location_line}"
            f"{description_block}\n"
            f"— The Heads Up Calendar Team"
        )

        try:
            # Send notification via Django email backend
            send_mail(
                subject=f"Heads Up Reminder: {event.title}",
                message=message_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "headsup475@gmail.com"),
                recipient_list=[user.email],
                fail_silently=False,
            )

            # Successfully delivered
            notification.status = NotificationQueue.Status.SENT
            notification.save(update_fields=["status"])
            results["sent"] += 1
            logger.info(f"Successfully sent reminder for event '{event.title}' to {user.email}")

        except Exception as exc:
            logger.warning(
                f"Failed to send reminder {notification.id} on attempt {notification.attempts}: {exc}"
            )
            # Retry up to 3 times before permanently marking as failed (SDD rule)
            if notification.attempts < 3:
                notification.status = NotificationQueue.Status.PENDING
                results["retrying"] += 1
            else:
                notification.status = NotificationQueue.Status.FAILED
                results["failed"] += 1

            notification.save(update_fields=["status"])

    return results
