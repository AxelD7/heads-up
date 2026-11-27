from django.conf import settings
from django.db import models


class NotificationQueue(models.Model):
    """
    Queue of scheduled notifications waiting to be sent to users for upcoming events.
    """
    class DeliveryMethod(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    # The calendar event this notification is reminding the user about
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # Recipient user of the notification
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    # The scheduled time when this notification should be sent out
    target_time = models.DateTimeField()
    # Method used to deliver the reminder (email or SMS)
    delivery_method = models.CharField(
        max_length=10,
        choices=DeliveryMethod.choices,
    )
    # Processing status of the reminder
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    # Counter for delivery attempts
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["target_time"]
        indexes = [
            models.Index(fields=["status", "target_time"], name="notif_status_target_idx"),
        ]

    def __str__(self):
        return f"{self.delivery_method} reminder for {self.event.title} at {self.target_time} ({self.status})"


class NotificationPreference(models.Model):
    """
    Stores per-user reminder preferences without modifying the CustomUser model.
    Currently email-only (SMS reminders are unavailable/disabled).
    """
    REMINDER_INTERVAL_CHOICES = [
        (1, "1 minute before"),
        (2, "2 minutes before"),
        (5, "5 minutes before"),
        (10, "10 minutes before"),
        (15, "15 minutes before"),
        (30, "30 minutes before"),
        (60, "1 hour before"),
        (1440, "1 day before"),
    ]

    # User who owns these notification settings
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
    )
    # Whether email reminders are enabled for this user
    email_enabled = models.BooleanField(default=True)
    # Optional custom email address for reminders (falls back to user.email if blank)
    notification_email = models.EmailField(blank=True)
    # How many minutes before an event the reminder should be scheduled
    reminder_minutes = models.PositiveIntegerField(
        choices=REMINDER_INTERVAL_CHOICES,
        default=60,
    )
    # SMS reminders are currently disabled/unavailable (email-only)
    sms_enabled = models.BooleanField(default=False)

    def __str__(self):
        status = "Enabled" if self.email_enabled else "Disabled"
        return f"Notification preferences for {self.user} (Email: {status})"
