from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse

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


class EventViewTestCase(TestCase):
    """
    Tests for Event CRUD views, authentication,
    ownership permissions, and form validation.
    """

    def setUp(self):
        User = get_user_model()

        # Creates two users to test event ownership.
        self.user = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="password123",
            phone_number="555-0200",
        )

        self.other_user = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="admin1thisisastrongpw",
            phone_number="555-0201",
        )

        self.client.force_login(self.user)

        # Creates an event belonging to the first user.
        self.start = timezone.localtime(
            timezone.now() + timedelta(days=1)
        ).replace(second=0, microsecond=0)

        self.end = self.start + timedelta(hours=1)

        self.event = Event.objects.create(
            user=self.user,
            title="Coding Grindsesh",
            start_time=self.start,
            end_time=self.end,
            location="The Basement",
            description="Surely HeadsUp will work at the end of this one",
        )

        # Create an event belonging to the second user.
        self.other_event = Event.objects.create(
            user=self.other_user,
            title="Other User Event",
            start_time=self.start,
            end_time=self.end,
        )

    def get_formatted_time(self, value):
        """
        Format datetime values for HTML datetime-local inputs.
        """
        return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")

    def test_event_list_only_shows_users_own_events(self):
        """
        Ensure users only see events belonging to their account.
        """
        response = self.client.get(reverse("events:event_list"))

        self.assertEqual(response.status_code, 200)

        events = list(response.context["events"])

        self.assertIn(self.event, events)
        self.assertNotIn(self.other_event, events)

    def test_user_can_view_own_event(self):
        """
        Ensure a user can view their own event.
        """
        response = self.client.get(
            reverse(
                "events:event_detail",
                kwargs={"pk": self.event.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], self.event)

    def test_user_cannot_view_another_users_event(self):
        """
        Ensure users cannot view events owned by other users.
        """
        response = self.client.get(
            reverse(
                "events:event_detail",
                kwargs={"pk": self.other_event.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_user_can_create_event(self):
        """
        Ensure an authenticated user can successfully create an event.
        """
        response = self.client.post(
            reverse("events:event_create"),
            {
                "title": "New Coding Grindsesh",
                "start_time": self.get_formatted_time(
                    self.start + timedelta(days=2)
                ),
                "end_time": self.get_formatted_time(
                    self.end + timedelta(days=2)
                ),
                "location": "My Basement",
                "description": "I love git",
                "category": Event.Category.ACADEMIC,
            },
        )

        self.assertEqual(response.status_code, 302)

        event = Event.objects.get(title="New Coding Grindsesh")

        self.assertEqual(event.user, self.user)
        self.assertEqual(
            event.category,
            Event.Category.ACADEMIC,
        )

    def test_event_creation_rejects_invalid_times(self):
        """
        Ensure an event cannot end before or at its start time.
        """
        start = self.start + timedelta(days=2)
        end = start - timedelta(hours=1)

        response = self.client.post(
            reverse("events:event_create"),
            {
                "title": "Invalid Event",
                "start_time": self.get_formatted_time(start),
                "end_time": self.get_formatted_time(end),
                "location": "",
                "description": "",
                "category": Event.Category.PERSONAL,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "End time must be after start time.",
            response.context["form"].errors["end_time"],
        )

        self.assertFalse(
            Event.objects.filter(title="Invalid Event").exists()
        )

    def test_user_can_update_own_event(self):
        """
        Ensure a user can update an event they own.
        """
        response = self.client.post(
            reverse(
                "events:event_update",
                kwargs={"pk": self.event.pk},
            ),
            {
                "title": "Updated Coding Session",
                "start_time": self.get_formatted_time(self.start),
                "end_time": self.get_formatted_time(self.end),
                "location": "Blizzard",
                "description": "Pullin the codecave",
                "category": Event.Category.ACADEMIC,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.event.refresh_from_db()

        self.assertEqual(
            self.event.title,
            "Updated Coding Session",
        )
        self.assertEqual(self.event.location, "Blizzard")
        self.assertEqual(self.event.user, self.user)

    def test_user_cannot_update_another_users_event(self):
        """
        Ensure a user cannot update an event owned by another user.
        """
        response = self.client.post(
            reverse(
                "events:event_update",
                kwargs={"pk": self.other_event.pk},
            ),
            {
                "title": "Unauthorized Update",
                "start_time": self.get_formatted_time(self.start),
                "end_time": self.get_formatted_time(self.end),
                "category": Event.Category.PERSONAL,
            },
        )

        self.assertEqual(response.status_code, 404)

        self.other_event.refresh_from_db()

        self.assertEqual(
            self.other_event.title,
            "Other User Event",
        )

    def test_user_can_delete_own_event(self):
        """
        Ensure a user can delete an event they own.
        """
        response = self.client.post(
            reverse(
                "events:event_delete",
                kwargs={"pk": self.event.pk},
            )
        )

        self.assertRedirects(
            response,
            reverse("events:event_list"),
        )

        self.assertFalse(
            Event.objects.filter(pk=self.event.pk).exists()
        )

    def test_user_cannot_delete_another_users_event(self):
        """
        Ensure a user cannot delete an event owned by another user.
        """
        response = self.client.post(
            reverse(
                "events:event_delete",
                kwargs={"pk": self.other_event.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

        self.assertTrue(
            Event.objects.filter(pk=self.other_event.pk).exists()
        )

    def test_delete_requires_post_request(self):
        """
        Ensure events cannot be deleted using GET requests.
        """
        response = self.client.get(
            reverse(
                "events:event_delete",
                kwargs={"pk": self.event.pk},
            )
        )

        self.assertEqual(response.status_code, 405)

        self.assertTrue(
            Event.objects.filter(pk=self.event.pk).exists()
        )

    def test_unauthenticated_user_cannot_access_events(self):
        """
        Ensure unauthenticated users are redirected to login.
        """
        self.client.logout()

        response = self.client.get(
            reverse("events:event_list")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)