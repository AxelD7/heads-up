from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from .models import Event, ExternalFeed
from .services import parse_ics_content, sync_ics_events


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
        # End time = starttime + 1 hour
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

    def test_dashboard_only_shows_users_own_events(self):
        """
        Ensure users only see events belonging to their account.
        """
        response = self.client.get(reverse("events:event_list"))

        self.assertEqual(response.status_code, 200)

        events = list(response.context["events"])

        self.assertIn(self.event, events)
        self.assertNotIn(self.other_event, events)

    def test_dashboard_context_serializes_owned_events_and_preferences(self):
        """
        Test to make sure past events stay in the calendar data but do not make it to the upcoming list.
        """
        past_event = Event.objects.create(
            user=self.user,
            title="Past event",
            start_time=timezone.now() - timedelta(days=2),
            end_time=timezone.now() - timedelta(days=2) + timedelta(hours=1),
        )
        self.user.date_format = "D/M/Y"
        self.user.time_format = "24h"
        self.user.save(update_fields=["date_format", "time_format"])

        response = self.client.get(reverse("events:event_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_format"], "D/M/Y")
        self.assertEqual(response.context["time_format"], "24h")
        self.assertEqual(response.context["date_fmt"], "j/n/Y")
        self.assertEqual(response.context["time_fmt"], "H:i")
        self.assertIn(self.event, response.context["events"])
        self.assertNotIn(past_event, response.context["events"])

        serialized_events = response.context["dashboard_events"]
        event_data = next(
            event for event in serialized_events if event["id"] == self.event.pk
        )
        self.assertEqual(
            event_data["start"], int(self.event.start_time.timestamp() * 1000)
        )
        self.assertEqual(
            event_data["end"], int(self.event.end_time.timestamp() * 1000)
        )
        self.assertEqual(event_data["category"], self.event.category)
        self.assertEqual(event_data["location"], self.event.location)
        self.assertEqual(event_data["description"], self.event.description)
        self.assertEqual(
            event_data["detail_url"],
            reverse("events:event_detail", kwargs={"pk": self.event.pk}),
        )
        self.assertTrue(
            any(event["id"] == past_event.pk for event in serialized_events)
        )
        self.assertFalse(
            any(event["id"] == self.other_event.pk for event in serialized_events)
        )

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

        self.assertRedirects(
            response,
            reverse("events:event_list"),
        )

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

    def test_delete_confirmation_page(self):
        """
        Ensure users can view the confirmation page before deleting
        their own event.
        """
        response = self.client.get(
            reverse(
                "events:event_delete_confirm",
                kwargs={"pk": self.event.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "events/event_confirm_delete.html"
        )
        self.assertEqual(response.context["event"], self.event)

        # Viewing confirmation must not delete the event.
        self.assertTrue(
            Event.objects.filter(pk=self.event.pk).exists()
        )


    def test_user_cannot_view_another_users_delete_confirmation(self):
        """
        Ensure users cannot access the deletion confirmation page
        for another user's event.
        """
        response = self.client.get(
            reverse(
                "events:event_delete_confirm",
                kwargs={"pk": self.other_event.pk},
            )
        )

        self.assertEqual(response.status_code, 404)


    def test_delete_requires_post_request(self):
        """
        Ensure the actual deletion endpoint rejects GET requests.
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


    def test_delete_confirmation_post_deletes_event(self):
        """
        Ensure submitting the confirmation form deletes the event.
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

    def test_unauthenticated_user_cannot_access_events(self):
        """
        Ensure unauthenticated users are redirected to login.
        """
        self.client.logout()

        response = self.client.get(
            reverse("events:event_list")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)


class IcalParserServiceTestCase(TestCase):
    """
    Test suite verifying the RFC 5545 .ics parser utility, SHA-256 hash generation,
    and duplicate-safe event synchronization.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="icaluser",
            email="ical@example.com",
            password="testpassword123",
            phone_number="555-0188",
        )

    def test_parse_standard_utc_vevent_and_hash(self):
        """
        Verify a standard UTC VEVENT is parsed into internal fields with a 64-character SHA-256 hash.
        """
        ics_data = (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:moodle-event-101\r\n"
            "SUMMARY:CIS 2999 Midterm\r\n"
            "DTSTART:20261201T140000Z\r\n"
            "DTEND:20261201T153000Z\r\n"
            "LOCATION:Dodge Hall 204\r\n"
            "DESCRIPTION:Bring a calculator.\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        parsed = parse_ics_content(ics_data)
        self.assertEqual(len(parsed), 1)

        item = parsed[0]
        expected_start = datetime(2026, 12, 1, 14, 0, tzinfo=dt_timezone.utc)
        expected_end = datetime(2026, 12, 1, 15, 30, tzinfo=dt_timezone.utc)

        self.assertEqual(item["external_id"], "moodle-event-101")
        self.assertEqual(item["title"], "CIS 2999 Midterm")
        self.assertEqual(item["start_time"], expected_start)
        self.assertEqual(item["end_time"], expected_end)
        self.assertEqual(item["location"], "Dodge Hall 204")
        self.assertEqual(item["description"], "Bring a calculator.")
        self.assertEqual(len(item["content_hash"]), 64)
        self.assertEqual(
            item["content_hash"],
            Event.build_hash(
                "CIS 2999 Midterm",
                expected_start,
                expected_end,
                "Dodge Hall 204",
                "Bring a calculator.",
            ),
        )

    def test_parse_folded_lines_escaped_chars_and_valarm(self):
        """
        Verify folded multi-line fields, escaped punctuation, and nested VALARM blocks
        are handled without corrupting the event's description.
        """
        ics_data = (
            "BEGIN:VCALENDAR\r\n"
            "BEGIN:VEVENT\r\n"
            "UID:google-uid-202\r\n"
            "SUMMARY:Team Meeting\\, Phase 2\\; Review\r\n"
            "DTSTART:20261202T180000Z\r\n"
            "DTEND:20261202T190000Z\r\n"
            "DESCRIPTION:Line one\\nLine two continues\r\n"
            "  on the next line\r\n"
            "BEGIN:VALARM\r\n"
            "ACTION:DISPLAY\r\n"
            "DESCRIPTION:This is an alarm reminder\r\n"
            "END:VALARM\r\n"
            "END:VEVENT\r\n"
            "END:VCALENDAR\r\n"
        )

        parsed = parse_ics_content(ics_data)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["title"], "Team Meeting, Phase 2; Review")
        self.assertEqual(parsed[0]["description"], "Line one\nLine two continues on the next line")

    def test_parse_all_day_and_missing_dtend_defaults(self):
        """
        Verify all-day events and events missing DTEND receive valid end_time > start_time.
        """
        ics_data = (
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "UID:allday-1\n"
            "SUMMARY:Final Project Due\n"
            "DTSTART;VALUE=DATE:20261210\n"
            "END:VEVENT\n"
            "BEGIN:VEVENT\n"
            "UID:notend-2\n"
            "SUMMARY:Assignment Deadline\n"
            "DTSTART:20261211T235900Z\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n"
        )

        parsed = parse_ics_content(ics_data)
        self.assertEqual(len(parsed), 2)

        # All-day defaults to 1 day duration
        self.assertEqual(parsed[0]["end_time"] - parsed[0]["start_time"], timedelta(days=1))
        # Timed event missing DTEND defaults to 1 hour duration
        self.assertEqual(parsed[1]["end_time"] - parsed[1]["start_time"], timedelta(hours=1))

    def test_sync_ics_events_creates_skips_and_updates(self):
        """
        Verify syncing .ics content creates new imported events, skips identical re-syncs
        without duplicating, and updates existing events when the SHA-256 hash changes.
        """
        feed = ExternalFeed.objects.create(
            user=self.user,
            source_type="Moodle",
            feed_url="https://moodle.oakland.edu/calendar/export.ics",
        )

        initial_ics = (
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "UID:moodle-999\n"
            "SUMMARY:Homework 4\n"
            "DTSTART:20261215T160000Z\n"
            "DTEND:20261215T170000Z\n"
            "LOCATION:Online\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n"
        )

        # 1. First sync creates the event
        res1 = sync_ics_events(self.user, initial_ics, feed=feed)
        self.assertEqual(res1["created"], 1)
        self.assertEqual(res1["updated"], 0)
        self.assertEqual(res1["skipped"], 0)
        feed.refresh_from_db()
        self.assertIsNotNone(feed.last_synced_at)

        event = Event.objects.get(feed=feed, external_id="moodle-999")
        self.assertTrue(event.is_imported)
        old_hash = event.content_hash

        # 2. Second sync with identical content skips (no duplicates)
        res2 = sync_ics_events(self.user, initial_ics, feed=feed)
        self.assertEqual(res2["created"], 0)
        self.assertEqual(res2["updated"], 0)
        self.assertEqual(res2["skipped"], 1)
        self.assertEqual(Event.objects.filter(feed=feed).count(), 1)

        # 3. Third sync with updated time and location updates the existing event and hash
        updated_ics = (
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "UID:moodle-999\n"
            "SUMMARY:Homework 4 (Extended)\n"
            "DTSTART:20261216T160000Z\n"
            "DTEND:20261216T170000Z\n"
            "LOCATION:Moodle Portal\n"
            "END:VEVENT\n"
            "END:VCALENDAR\n"
        )
        res3 = sync_ics_events(self.user, updated_ics, feed=feed)
        self.assertEqual(res3["created"], 0)
        self.assertEqual(res3["updated"], 1)
        self.assertEqual(res3["skipped"], 0)

        event.refresh_from_db()
        self.assertEqual(event.title, "Homework 4 (Extended)")
        self.assertEqual(event.location, "Moodle Portal")
        self.assertNotEqual(event.content_hash, old_hash)
        self.assertEqual(Event.objects.filter(feed=feed).count(), 1)


class CalendarDashboardAndImportTestCase(TestCase):
    """
    Test suite verifying the FullCalendar dashboard source filtering (Moodle vs Google),
    the calendar import view, and feed ownership security.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="caluser",
            email="cal@example.com",
            password="testpassword123",
            phone_number="555-0177",
        )
        self.other_user = get_user_model().objects.create_user(
            username="othercaluser",
            email="othercal@example.com",
            password="testpassword123",
            phone_number="555-0178",
        )
        self.client.force_login(self.user)
        self.now = timezone.now()

        self.moodle_feed = ExternalFeed.objects.create(
            user=self.user,
            source_type="Moodle",
            feed_url="https://moodle.example.com/cal.ics",
        )
        self.google_feed = ExternalFeed.objects.create(
            user=self.user,
            source_type="Google",
            feed_url="https://calendar.google.com/cal.ics",
        )

        self.moodle_event = Event.objects.create(
            user=self.user,
            feed=self.moodle_feed,
            title="Moodle Quiz",
            start_time=self.now + timedelta(days=1),
            end_time=self.now + timedelta(days=1, hours=1),
            is_imported=True,
            external_id="m1",
        )
        self.google_event = Event.objects.create(
            user=self.user,
            feed=self.google_feed,
            title="Google Dentist",
            start_time=self.now + timedelta(days=2),
            end_time=self.now + timedelta(days=2, hours=1),
            is_imported=True,
            external_id="g1",
        )
        self.manual_event = Event.objects.create(
            user=self.user,
            title="Manual Study",
            start_time=self.now + timedelta(days=3),
            end_time=self.now + timedelta(days=3, hours=1),
        )

    def test_dashboard_source_filtering_moodle_and_google(self):
        """
        Main dashboard shows all user events untouched, while dedicated Moodle and Google
        sidebar tabs filter accurately to each external source.
        """
        # Main Calendar tab (All events)
        resp_all = self.client.get(reverse("events:event_list"))
        self.assertEqual(resp_all.status_code, 200)
        self.assertEqual(len(resp_all.context["dashboard_events"]), 3)

        # Moodle tab (/calendar/Moodle/)
        resp_moodle = self.client.get(reverse("events:source_calendar", kwargs={"source": "Moodle"}))
        self.assertEqual(resp_moodle.status_code, 200)
        self.assertTemplateUsed(resp_moodle, "events/source_calendar.html")
        moodle_titles = [e["title"] for e in resp_moodle.context["calendar_events"]]
        self.assertEqual(moodle_titles, ["Moodle Quiz"])

        # Google Calendar tab (/calendar/Google/)
        resp_google = self.client.get(reverse("events:source_calendar", kwargs={"source": "Google"}))
        self.assertEqual(resp_google.status_code, 200)
        self.assertTemplateUsed(resp_google, "events/source_calendar.html")
        google_titles = [e["title"] for e in resp_google.context["calendar_events"]]
        self.assertEqual(google_titles, ["Google Dentist"])

    def test_import_calendar_uploaded_ics_file(self):
        """
        Uploading a valid .ics file on /import/ creates the ExternalFeed and Event records.
        """
        ics_bytes = (
            b"BEGIN:VCALENDAR\r\n"
            b"BEGIN:VEVENT\r\n"
            b"UID:upload-123\r\n"
            b"SUMMARY:Uploaded Lab Session\r\n"
            b"DTSTART:20261220T150000Z\r\n"
            b"DTEND:20261220T160000Z\r\n"
            b"END:VEVENT\r\n"
            b"END:VCALENDAR\r\n"
        )
        uploaded = SimpleUploadedFile("moodle.ics", ics_bytes, content_type="text/calendar")

        response = self.client.post(
            reverse("events:import_calendar"),
            data={
                "source_type": "Moodle",
                "category": "academic",
                "ics_file": uploaded,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Event.objects.filter(
                user=self.user,
                title="Uploaded Lab Session",
                is_imported=True,
                feed__source_type="Moodle",
            ).exists()
        )

    def test_import_calendar_requires_url_or_file(self):
        """
        Submitting the import form with neither URL nor file must fail validation.
        """
        response = self.client.post(
            reverse("events:import_calendar"),
            data={"source_type": "Moodle", "category": "academic"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())

    def test_other_user_cannot_delete_or_sync_feed(self):
        """
        Users must receive 404 when attempting to sync or delete another user's feed.
        """
        other_feed = ExternalFeed.objects.create(
            user=self.other_user,
            source_type="Google",
            feed_url="https://calendar.google.com/other.ics",
        )
        resp_sync = self.client.post(reverse("events:sync_feed", kwargs={"pk": other_feed.pk}))
        resp_del = self.client.post(reverse("events:delete_feed", kwargs={"pk": other_feed.pk}))
        self.assertEqual(resp_sync.status_code, 404)
        self.assertEqual(resp_del.status_code, 404)


@override_settings(
    GOOGLE_CLIENT_ID="test-client-id.apps.googleusercontent.com",
    GOOGLE_CLIENT_SECRET="test-secret",
    GOOGLE_REDIRECT_URI="http://127.0.0.1:8000/google/callback/",
)
class GoogleCalendarAPITestCase(TestCase):
    """
    Test suite verifying Google OAuth 2.0 flow, CSRF state verification,
    UTC conversion of Google Calendar events, and SHA-256 duplicate prevention.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="gcaluser",
            email="gcal@example.com",
            password="testpassword123",
            phone_number="555-0166",
        )
        self.client.force_login(self.user)

    def test_google_connect_redirects_with_oauth_state(self):
        """
        Visiting /google/connect/ must store a CSRF state in session and redirect to Google.
        """
        response = self.client.get(reverse("events:google_connect"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("https://accounts.google.com/o/oauth2/v2/auth", response.url)
        self.assertIn("client_id=test-client-id.apps.googleusercontent.com", response.url)
        self.assertIn("calendar.readonly", response.url)
        self.assertIn("google_oauth_state", self.client.session)

    def test_google_callback_rejects_invalid_state(self):
        """
        Callback must reject requests whose OAuth state does not match the session state.
        """
        session = self.client.session
        session["google_oauth_state"] = "expected-state"
        session.save()

        response = self.client.get(
            reverse("events:google_callback"),
            data={"state": "wrong-state", "code": "abc"},
        )
        self.assertRedirects(response, reverse("events:import_calendar"))
        self.assertEqual(Event.objects.filter(user=self.user).count(), 0)

    @patch("events.views.exchange_code_for_tokens", return_value={"access_token": "fake-token"})
    @patch("events.google_calendar.fetch_google_calendar_events")
    def test_google_callback_imports_and_deduplicates_events(self, mock_fetch, mock_exchange):
        """
        OAuth callback must import timed and all-day events, skip canceled ones,
        and prevent duplicates on subsequent syncs.
        """
        mock_fetch.return_value = [
            {
                "id": "google-evt-1",
                "status": "confirmed",
                "summary": "Doctor Appointment",
                "location": "Clinic",
                "description": "Annual checkup",
                "start": {"dateTime": "2026-12-05T10:00:00-05:00"},
                "end": {"dateTime": "2026-12-05T11:00:00-05:00"},
            },
            {
                "id": "google-evt-2",
                "status": "confirmed",
                "summary": "Holiday Break",
                "start": {"date": "2026-12-25"},
                "end": {"date": "2026-12-26"},
            },
            {
                "id": "google-evt-3",
                "status": "cancelled",
                "summary": "Canceled Meeting",
                "start": {"dateTime": "2026-12-06T12:00:00Z"},
            },
        ]

        session = self.client.session
        session["google_oauth_state"] = "valid-state"
        session.save()

        response = self.client.get(
            reverse("events:google_callback"),
            data={"state": "valid-state", "code": "auth-code-123"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("events:source_calendar", kwargs={"source": "Google"}),
        )

        # 2 confirmed events imported, 1 cancelled skipped
        events = Event.objects.filter(user=self.user, feed__source_type="Google")
        self.assertEqual(events.count(), 2)

        appt = events.get(external_id="google-evt-1")
        self.assertTrue(appt.is_imported)
        # 10:00 AM EST (-05:00) == 15:00 UTC
        self.assertEqual(appt.start_time, datetime(2026, 12, 5, 15, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(len(appt.content_hash), 64)

        # Re-syncing identical data via sync_feed must skip duplicates
        feed = appt.feed
        resp_resync = self.client.post(reverse("events:sync_feed", kwargs={"pk": feed.pk}))
        self.assertEqual(resp_resync.status_code, 302)
        self.assertEqual(Event.objects.filter(feed=feed).count(), 2)

    @patch("events.google_calendar.fetch_google_calendar_events")
    def test_sync_google_events_updates_changed_event(self, mock_fetch):
        """
        If an event changes on Google Calendar, re-syncing updates the existing row
        rather than creating a duplicate.
        """
        from .google_calendar import sync_google_events

        mock_fetch.return_value = [
            {
                "id": "google-evt-99",
                "status": "confirmed",
                "summary": "Original Title",
                "start": {"dateTime": "2026-12-10T14:00:00Z"},
                "end": {"dateTime": "2026-12-10T15:00:00Z"},
            }
        ]
        res1 = sync_google_events(self.user, "fake-token")
        self.assertEqual(res1["created"], 1)

        mock_fetch.return_value = [
            {
                "id": "google-evt-99",
                "status": "confirmed",
                "summary": "Updated Title",
                "location": "Room 300",
                "start": {"dateTime": "2026-12-10T16:00:00Z"},
                "end": {"dateTime": "2026-12-10T17:00:00Z"},
            }
        ]
        res2 = sync_google_events(self.user, "fake-token")
        self.assertEqual(res2["created"], 0)
        self.assertEqual(res2["updated"], 1)

        evt = Event.objects.get(user=self.user, external_id="google-evt-99")
        self.assertEqual(evt.title, "Updated Title")
        self.assertEqual(evt.location, "Room 300")
