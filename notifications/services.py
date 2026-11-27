from datetime import timedelta
import logging
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import NotificationPreference, NotificationQueue

logger = logging.getLogger(__name__)


def cancel_notifications_for_event(event):
    """
    Mark all pending notifications for a given event as canceled.
    Leaves already sent, failed, or processing rows untouched.
    """
    return NotificationQueue.objects.filter(
        event=event,
        status=NotificationQueue.Status.PENDING,
    ).update(status=NotificationQueue.Status.CANCELED)


def cancel_user_pending_notifications(user):
    """
    Mark all pending notifications for a user as canceled (used when notifications are disabled).
    """
    return NotificationQueue.objects.filter(
        user=user,
        status=NotificationQueue.Status.PENDING,
    ).update(status=NotificationQueue.Status.CANCELED)


def queue_notifications_for_event(event):
    """
    Recalculates and schedules pending reminders for a given calendar event.
    
    1. Cancels any existing pending reminders for this event.
    2. Checks user NotificationPreference (skips queuing if disabled).
    3. Calculates target reminder times (start_time - interval).
    4. Queues new pending reminder rows for any target time still in the future.
    """
    # Read global reminder defaults from settings (or fall back to defaults)
    intervals = getattr(settings, "NOTIFICATION_DEFAULT_INTERVALS_MINUTES", [60])
    methods = getattr(settings, "NOTIFICATION_DEFAULT_METHODS", ["email"])

    user = event.user
    pref = NotificationPreference.objects.filter(user=user).first()

    # Respect NotificationPreference if the user has configured settings
    if pref is not None:
        if not pref.email_enabled:
            with transaction.atomic():
                cancel_notifications_for_event(event)
            return []
        intervals = [pref.reminder_minutes]
        methods = [NotificationQueue.DeliveryMethod.EMAIL]

    # Also support custom attributes if added directly on CustomUser in the future
    if hasattr(user, "notification_intervals") and getattr(user, "notification_intervals"):
        intervals = getattr(user, "notification_intervals")
    if hasattr(user, "notification_methods") and getattr(user, "notification_methods"):
        methods = getattr(user, "notification_methods")

    created_rows = []
    now = timezone.now()

    with transaction.atomic():
        # a) Cancel all currently pending reminders for this event
        cancel_notifications_for_event(event)

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
    Queries pending reminders whose target time has arrived, atomically claims each row
    as 'processing' to prevent duplicate sends, dispatches email via Django SMTP/console,
    and updates status to 'sent' or 'failed' (retrying up to 3 times).
    """
    now = timezone.now()

    # Query all pending email reminders due to be sent now or earlier
    due_notifications = NotificationQueue.objects.filter(
        status=NotificationQueue.Status.PENDING,
        delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
        target_time__lte=now,
    ).select_related("event", "user")

    results = {
        "total": 0,
        "sent": 0,
        "retrying": 0,
        "failed": 0,
    }

    for notification in due_notifications:
        # Atomic compare-and-set claim: only claim rows that are still PENDING
        with transaction.atomic():
            claimed = NotificationQueue.objects.filter(
                pk=notification.pk,
                status=NotificationQueue.Status.PENDING,
            ).update(
                status=NotificationQueue.Status.PROCESSING,
                attempts=F("attempts") + 1,
            )
            if claimed == 0:
                continue
            notification.refresh_from_db(fields=["status", "attempts"])

        results["total"] += 1
        event = notification.event
        user = notification.user
        pref = NotificationPreference.objects.filter(user=user).first()
        recipient_email = (
            pref.notification_email
            if pref and pref.notification_email
            else user.email
        )

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
            if not recipient_email:
                raise ValueError("Recipient user has no email address configured.")

            # Send notification via configured Django email backend (SMTP or console)
            send_mail(
                subject=f"Heads Up Reminder: {event.title}",
                message=message_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "headsup475@gmail.com"),
                recipient_list=[recipient_email],
                fail_silently=False,
            )

            # Successfully delivered
            notification.status = NotificationQueue.Status.SENT
            notification.save(update_fields=["status"])
            results["sent"] += 1
            logger.info(f"Successfully sent reminder for event '{event.title}' to {recipient_email}")

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
