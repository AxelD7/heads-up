from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """
    Application configuration for notifications.
    Registers signal handlers to schedule reminders whenever events are saved.
    """
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"

    def ready(self):
        # Connect signal receivers when Django starts up
        import notifications.signals  # noqa: F401
