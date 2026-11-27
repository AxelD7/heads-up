from django.contrib import admin
from .models import NotificationPreference, NotificationQueue


@admin.register(NotificationQueue)
class NotificationQueueAdmin(admin.ModelAdmin):
    """
    Admin interface configuration for reviewing and managing scheduled notifications.
    """
    list_display = (
        "event",
        "user",
        "delivery_method",
        "target_time",
        "status",
        "attempts",
    )
    list_filter = ("status", "delivery_method")


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    """
    Admin interface configuration for per-user notification preferences.
    """
    list_display = ("user", "email_enabled", "notification_email", "reminder_minutes", "sms_enabled")
    list_filter = ("email_enabled",)
