from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import Event, ExternalFeed


class EventModelTestCase(TestCase):
    """
    Test suite verifying core Event and ExternalFeed model behaviors,
    validation rules, database constraints, and hashing utilities.
    """

    def setUp(self):
        # Create a test user instance using get_user_model()
        # Including phone_number to satisfy CustomUser model requirements
        self.user = get_user_model().objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpassword123",
            phone_number="555-0199",
        )
        self.now = timezone.now()

    def test_valid_event_defaults(self):
        """
        Ensure a valid event saves properly and applies default values:
        category='personal' and is_imported=False.
        """
        start = self.now + timedelta(days=1)
        end = start + timedelta(hours=2)

        event = Event(
            user=self.user,
            title="Study Session",
            start_time=start,
            end_time=end,
            location="Library Room 204",
            description="Preparing for midterms",
        )
        # Validate model clean() passes
        event.full_clean()
        event.save()

        # Check stored defaults and representation
        self.assertIsNotNone(event.pk)
        self.assertEqual(event.category, Event.Category.PERSONAL)
        self.assertFalse(event.is_imported)
        self.assertEqual(str(event), "Study Session")

    def test_end_time_before_start_time_fails_clean(self):
        """
        Validate that end_time occurring before start_time raises a ValidationError in full_clean().
        """
        start = self.now + timedelta(hours=2)
        end = self.now + timedelta(hours=1)

        event = Event(
            user=self.user,
            title="Invalid Chronology Event",
            start_time=start,
            end_time=end,
        )

        with self.assertRaises(ValidationError) as context:
            event.full_clean()

        self.assertIn("End time must be after start time.", str(context.exception))

    def test_end_time_equal_start_time_fails_clean(self):
        """
        Validate that end_time equal to start_time raises a ValidationError in full_clean().
        """
        start = self.now + timedelta(hours=2)
        end = start

        event = Event(
            user=self.user,
            title="Zero Duration Event",
            start_time=start,
            end_time=end,
        )

        with self.assertRaises(ValidationError) as context:
            event.full_clean()

        self.assertIn("End time must be after start time.", str(context.exception))

    def test_two_manual_events_with_blank_external_id(self):
        """
        Ensure two manual events with blank external_id can both be saved
        without triggering unique constraint conflicts.
        """
        start = self.now + timedelta(days=2)
        end = start + timedelta(hours=1)

        event1 = Event.objects.create(
            user=self.user,
            title="Manual Task 1",
            start_time=start,
            end_time=end,
            external_id="",
        )

        event2 = Event.objects.create(
            user=self.user,
            title="Manual Task 2",
            start_time=start + timedelta(hours=2),
            end_time=end + timedelta(hours=2),
            external_id="",
        )

        self.assertIsNotNone(event1.pk)
        self.assertIsNotNone(event2.pk)
        self.assertEqual(Event.objects.filter(user=self.user).count(), 2)

    def test_duplicate_feed_and_external_id_raises_integrity_error(self):
        """
        Ensure two events with the same feed and the same non-blank external_id
        raise an IntegrityError due to the unique_feed_external_id constraint.
        """
        feed = ExternalFeed.objects.create(
            user=self.user,
            source_type="Google",
            feed_url="https://calendar.google.com/test_feed",
        )
        self.assertEqual(str(feed), f"Google ({self.user})")

        start = self.now + timedelta(days=3)
        end = start + timedelta(hours=1)

        # First imported event with external_id
        Event.objects.create(
            user=self.user,
            feed=feed,
            title="Lecture 1",
            start_time=start,
            end_time=end,
            is_imported=True,
            external_id="ext-unique-999",
        )

        # Attempt to save a second event with the identical feed and external_id
        duplicate_event = Event(
            user=self.user,
            feed=feed,
            title="Lecture 1 Duplicate",
            start_time=start + timedelta(days=1),
            end_time=end + timedelta(days=1),
            is_imported=True,
            external_id="ext-unique-999",
        )

        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                duplicate_event.save()

    def test_build_hash(self):
        """
        Validate build_hash returns a 64-character SHA-256 hex string and
        produces a different hash when the description or other fields change.
        """
        title = "Team Meeting"
        start = "2026-11-10T10:00:00Z"
        end = "2026-11-10T11:00:00Z"
        location = "Room 101"
        desc1 = "Reviewing project timeline"
        desc2 = "Reviewing project timeline and deliverables"

        hash1 = Event.build_hash(title, start, end, location, desc1)
        hash2 = Event.build_hash(title, start, end, location, desc2)

        # Verify hash lengths (SHA-256 produces 64 hex characters)
        self.assertEqual(len(hash1), 64)
        self.assertEqual(len(hash2), 64)

        # Verify hash changes when content changes
        self.assertNotEqual(hash1, hash2)
