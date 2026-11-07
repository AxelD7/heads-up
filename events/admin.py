from django.contrib import admin
from .models import Event, ExternalFeed


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """
    Admin configuration for the Event model.
    """
    # Columns displayed in the event list table
    list_display = (
        "title",
        "user",
        "category",
        "start_time",
        "end_time",
        "is_imported",
    )
    # Sidebar filters for categorization and import status
    list_filter = ("category", "is_imported")
    # Searchable fields for events
    search_fields = ("title", "description", "external_id")


@admin.register(ExternalFeed)
class ExternalFeedAdmin(admin.ModelAdmin):
    """
    Admin configuration for the ExternalFeed model.
    """
    # Columns displayed in the external feed list table
    list_display = ("source_type", "user", "last_synced_at")
