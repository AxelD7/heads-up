from django.contrib import admin
from .models import NotificationQueue


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
