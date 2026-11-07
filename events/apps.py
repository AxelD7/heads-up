from django.apps import AppConfig


class EventsConfig(AppConfig):
    """
    Application configuration for the events app, which manages
    calendar events and external calendar feeds.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'events'
