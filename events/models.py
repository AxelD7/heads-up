import hashlib
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, UniqueConstraint


class ExternalFeed(models.Model):
    """
    Represents an external calendar source (e.g., Google Calendar, Moodle, OUSail)
    connected to a user's account for event synchronization.
    """
    # Owner of the external calendar feed
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_feeds",
    )
    # Type of source: Google, Moodle, OUSail, etc.
    source_type = models.CharField(max_length=50)
    # Webcal/iCal (.ics) or API feed URL
    feed_url = models.URLField(max_length=500, blank=True)
    # Timestamp of the most recent successful synchronization
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.source_type} ({self.user})"


class Event(models.Model):
    """
    Core calendar event model storing both manually created user events
    and events imported from external feeds.
    """
    class Category(models.TextChoices):
        ACADEMIC = "academic", "Academic"
        PERSONAL = "personal", "Personal"
        WORK = "work", "Work"

    # User who owns this event
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
    )
    # Name or summary of the event
    title = models.CharField(max_length=200)
    # Start and end timestamps stored in UTC
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    # Physical or virtual location of the event
    location = models.CharField(max_length=200, blank=True)
    # Detailed event description or notes
    description = models.TextField(blank=True)
    # Classification category (academic, personal, work)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.PERSONAL,
    )
    # Flag indicating whether this event was imported from an external source
    is_imported = models.BooleanField(default=False)
    # Identifier from the external calendar system (e.g. iCal UID or Google event ID)
    external_id = models.CharField(max_length=255, blank=True)
    # SHA-256 hash used to detect content changes upon re-synchronization
    content_hash = models.CharField(max_length=64, blank=True)
    # Optional link to the originating external feed
    feed = models.ForeignKey(
        ExternalFeed,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="events",
    )

    class Meta:
        ordering = ["start_time"]
        constraints = [
            # Prevent duplicate imported events for the same feed and non-blank external_id
            UniqueConstraint(
                fields=["feed", "external_id"],
                condition=~Q(external_id=""),
                name="unique_feed_external_id",
            )
        ]

    def clean(self):
        """
        Validate that the event end time is strictly after the start time.
        """
        super().clean()
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError("End time must be after start time.")

    @staticmethod
    def build_hash(title, start_time, end_time, location, description):
        """
        Compute SHA-256 hex digest for event content comparison and deduplication.
        Format: f"{title}|{start_time}|{end_time}|{location}|{description}"
        """
        raw_content = f"{title}|{start_time}|{end_time}|{location}|{description}"
        return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()

    def __str__(self):
        return self.title
