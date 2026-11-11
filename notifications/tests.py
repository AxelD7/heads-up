from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from events.models import Event
from .models import NotificationQueue


class NotificationQueueTestCase(TestCase):
    """
    Automated test suite verifying NotificationQueue model behaviors,
    post-save signal event triggers, status transitions, and setting overrides.
    """

    def setUp(self):
        # Create a primary test user
        self.user = get_user_model().objects.create_user(
            username="austin",
            email="austin@example.com",
            password="securepassword123",
            phone_number="555-0101",
        )
        self.now = timezone.now()

    def test_new_future_event_creates_default_pending_notification(self):
        """
        Saving a new event far in the future should queue 1 pending reminder
        with target_time = start_time - 60 minutes for the event's user.
        """
        start = self.now + timedelta(hours=3)
        end = start + timedelta(hours=1)

        event = Event.objects.create(
            user=self.user,
            title="Software Engineering Lecture",
            start_time=start,
            end_time=end,
        )

        notifications = NotificationQueue.objects.filter(event=event)
        self.assertEqual(notifications.count(), 1)

        notif = notifications.first()
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.delivery_method, NotificationQueue.DeliveryMethod.EMAIL)
        self.assertEqual(notif.status, NotificationQueue.Status.PENDING)
        self.assertEqual(notif.target_time, start - timedelta(minutes=60))
        self.assertEqual(notif.attempts, 0)
        self.assertIn("email reminder for Software Engineering Lecture", str(notif))

    def test_event_starting_sooner_than_interval_creates_no_notification(self):
        """
        An event starting in 30 minutes has a reminder target time in the past
        (30m - 60m = 30m ago), so no notification row should be queued.
        """
        start = self.now + timedelta(minutes=30)
        end = start + timedelta(hours=1)

        event = Event.objects.create(
            user=self.user,
            title="Impending Meeting",
            start_time=start,
            end_time=end,
        )

        self.assertEqual(NotificationQueue.objects.filter(event=event).count(), 0)

    def test_updating_start_time_cancels_old_and_creates_new_pending_notification(self):
        """
        Editing an event's start time should cancel the previously scheduled pending reminder
        and create a newly recalculated pending reminder.
        """
        start1 = self.now + timedelta(hours=3)
        event = Event.objects.create(
            user=self.user,
            title="Rescheduled Exam",
            start_time=start1,
            end_time=start1 + timedelta(hours=2),
        )

        old_notif = NotificationQueue.objects.get(event=event, status=NotificationQueue.Status.PENDING)
        self.assertEqual(old_notif.target_time, start1 - timedelta(minutes=60))

        # Push the event forward by 2 hours
        start2 = self.now + timedelta(hours=5)
        event.start_time = start2
        event.end_time = start2 + timedelta(hours=2)
        event.save()

        # The old row must now be canceled
        old_notif.refresh_from_db()
        self.assertEqual(old_notif.status, NotificationQueue.Status.CANCELED)

        # A new pending row must be present with the new target time
        new_notif = NotificationQueue.objects.get(event=event, status=NotificationQueue.Status.PENDING)
        self.assertEqual(new_notif.target_time, start2 - timedelta(minutes=60))
        self.assertEqual(NotificationQueue.objects.filter(event=event).count(), 2)

    def test_resaving_event_without_changes_leaves_exactly_one_pending_notification(self):
        """
        Saving an event again without altering dates should leave exactly one pending reminder,
        with any prior pending reminder marked as canceled (avoiding duplicate alerts).
        """
        start = self.now + timedelta(hours=4)
        event = Event.objects.create(
            user=self.user,
            title="Project Check-in",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        # Save the event again without modifying it
        event.save()

        pending_count = NotificationQueue.objects.filter(
            event=event,
            status=NotificationQueue.Status.PENDING,
        ).count()
        canceled_count = NotificationQueue.objects.filter(
            event=event,
            status=NotificationQueue.Status.CANCELED,
        ).count()

        self.assertEqual(pending_count, 1)
        self.assertEqual(canceled_count, 1)

    def test_sent_notifications_not_changed_on_resave(self):
        """
        A reminder that has already been marked as 'sent' must not be altered or canceled
        when the event is re-saved.
        """
        start = self.now + timedelta(hours=4)
        event = Event.objects.create(
            user=self.user,
            title="Presentation",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        notif = NotificationQueue.objects.get(event=event)
        notif.status = NotificationQueue.Status.SENT
        notif.save()

        # Save event again
        event.save()

        # Original notification remains marked as sent
        notif.refresh_from_db()
        self.assertEqual(notif.status, NotificationQueue.Status.SENT)

    @override_settings(
        NOTIFICATION_DEFAULT_INTERVALS_MINUTES=[15, 60],
        NOTIFICATION_DEFAULT_METHODS=["email", "sms"],
    )
    def test_override_settings_creates_row_per_interval_and_method_combination(self):
        """
        Overriding settings to provide multiple intervals [15, 60] and multiple methods [email, sms]
        should generate 2 x 2 = 4 pending notifications for a future event.
        """
        start = self.now + timedelta(hours=3)
        event = Event.objects.create(
            user=self.user,
            title="Campus Hackathon",
            start_time=start,
            end_time=start + timedelta(hours=5),
        )

        notifications = NotificationQueue.objects.filter(event=event, status=NotificationQueue.Status.PENDING)
        self.assertEqual(notifications.count(), 4)

        # Check that both 15-minute and 60-minute targets exist for both email and sms
        target_15 = start - timedelta(minutes=15)
        target_60 = start - timedelta(minutes=60)

        self.assertTrue(notifications.filter(target_time=target_15, delivery_method="email").exists())
        self.assertTrue(notifications.filter(target_time=target_15, delivery_method="sms").exists())
        self.assertTrue(notifications.filter(target_time=target_60, delivery_method="email").exists())
        self.assertTrue(notifications.filter(target_time=target_60, delivery_method="sms").exists())

    def test_deleting_event_removes_notification_rows(self):
        """
        Deleting an event must cascade delete all associated notification queue rows.
        """
        start = self.now + timedelta(hours=3)
        event = Event.objects.create(
            user=self.user,
            title="Canceled Workshop",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        event_id = event.id
        self.assertEqual(NotificationQueue.objects.filter(event_id=event_id).count(), 1)
        
        event.delete()
        self.assertEqual(NotificationQueue.objects.filter(event_id=event_id).count(), 0)

    def test_events_from_different_users_create_rows_for_own_owner(self):
        """
        Events created by different users should each queue notifications for their own owner.
        """
        user2 = get_user_model().objects.create_user(
            username="axel",
            email="axel@example.com",
            password="securepassword456",
            phone_number="555-0102",
        )

        start = self.now + timedelta(hours=3)
        event1 = Event.objects.create(
            user=self.user,
            title="Austin's Event",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )
        event2 = Event.objects.create(
            user=user2,
            title="Axel's Event",
            start_time=start,
            end_time=start + timedelta(hours=1),
        )

        notif1 = NotificationQueue.objects.get(event=event1)
        notif2 = NotificationQueue.objects.get(event=event2)

        self.assertEqual(notif1.user, self.user)
        self.assertEqual(notif2.user, user2)
