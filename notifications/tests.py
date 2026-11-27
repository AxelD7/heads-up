from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import Event
from .models import NotificationPreference, NotificationQueue
from .services import cancel_notifications_for_event, send_due_notifications


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


class EmailNotificationDispatcherTestCase(TestCase):
    """
    Test suite verifying the email dispatch worker, atomic status updates,
    content formatting, 3-attempt retry policy, and management command.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dispatcheruser",
            email="recipient@example.com",
            password="securepassword789",
            phone_number="555-0199",
        )
        self.now = timezone.now()

        # Create an event starting in 30 minutes
        self.event = Event.objects.create(
            user=self.user,
            title="CIS 2999 Presentation",
            start_time=self.now + timedelta(minutes=30),
            end_time=self.now + timedelta(minutes=90),
            location="Room 101",
            description="Final project demonstration.",
        )

    def test_send_due_notifications_success(self):
        """
        A due pending email notification should be sent via send_mail,
        updated to status='sent', and increment attempts to 1.
        """
        # Create a notification whose target_time is in the past (due right now)
        notification = NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now - timedelta(minutes=5),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PENDING,
            attempts=0,
        )

        results = send_due_notifications()

        self.assertEqual(results["total"], 1)
        self.assertEqual(results["sent"], 1)
        self.assertEqual(results["failed"], 0)

        # Verify email was dispatched to test outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertIn("CIS 2999 Presentation", sent_email.subject)
        self.assertIn("recipient@example.com", sent_email.to)
        self.assertIn("Room 101", sent_email.body)
        self.assertIn("Final project demonstration", sent_email.body)

        # Verify database record updated
        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationQueue.Status.SENT)
        self.assertEqual(notification.attempts, 1)

    def test_future_notifications_not_sent(self):
        """
        A pending notification scheduled for the future should NOT be sent.
        """
        NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now + timedelta(hours=2),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PENDING,
        )

        results = send_due_notifications()

        self.assertEqual(results["total"], 0)
        self.assertEqual(len(mail.outbox), 0)

    @patch("notifications.services.send_mail", side_effect=Exception("SMTP Connection Error"))
    def test_send_failure_retries_if_under_three_attempts(self, mock_send_mail):
        """
        If sending fails and attempts < 3, the status should revert to 'pending'
        so it can be retried on the next worker run.
        """
        notification = NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now - timedelta(minutes=1),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PENDING,
            attempts=0,
        )

        # First failure (attempts becomes 1 < 3) -> retrying
        results = send_due_notifications()
        self.assertEqual(results["retrying"], 1)
        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationQueue.Status.PENDING)
        self.assertEqual(notification.attempts, 1)

        # Second failure (attempts becomes 2 < 3) -> retrying
        results = send_due_notifications()
        self.assertEqual(results["retrying"], 1)
        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationQueue.Status.PENDING)
        self.assertEqual(notification.attempts, 2)

        # Third failure (attempts becomes 3 >= 3) -> marked FAILED permanently
        results = send_due_notifications()
        self.assertEqual(results["failed"], 1)
        notification.refresh_from_db()
        self.assertEqual(notification.status, NotificationQueue.Status.FAILED)
        self.assertEqual(notification.attempts, 3)

    def test_management_command_send_notifications(self):
        """
        The 'send_notifications' management command should execute cleanly from CLI.
        """
        NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now - timedelta(minutes=2),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PENDING,
        )

        # Call the management command
        call_command("send_notifications")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(NotificationQueue.objects.filter(status=NotificationQueue.Status.SENT).count(), 1)

    def test_management_command_send_reminders(self):
        """
        Running 'python manage.py send_reminders' must dispatch due email reminders
        and mark them as sent.
        """
        NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now - timedelta(minutes=2),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PENDING,
        )

        call_command("send_reminders")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(NotificationQueue.objects.filter(status=NotificationQueue.Status.SENT).count(), 1)

    def test_processing_rows_are_not_sent_again(self):
        """
        Rows already marked as 'processing' must not be picked up or sent twice.
        """
        NotificationQueue.objects.create(
            event=self.event,
            user=self.user,
            target_time=self.now - timedelta(minutes=2),
            delivery_method=NotificationQueue.DeliveryMethod.EMAIL,
            status=NotificationQueue.Status.PROCESSING,
        )

        results = send_due_notifications()

        self.assertEqual(results["total"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_deleting_event_cancels_pending_reminders_so_no_alert_is_sent(self):
        """
        Deleting an event triggers pre_delete cleanup so its pending reminders
        are canceled and no email is ever dispatched for the deleted event.
        """
        future_event = Event.objects.create(
            user=self.user,
            title="Event To Delete",
            start_time=self.now + timedelta(hours=3),
            end_time=self.now + timedelta(hours=4),
        )
        # Backdate target_time so it would otherwise be due
        notif = NotificationQueue.objects.get(event=future_event)
        notif.target_time = self.now - timedelta(minutes=1)
        notif.save()

        # Verify cancel_notifications_for_event directly marks pending rows as canceled
        with patch("notifications.signals.cancel_notifications_for_event", wraps=cancel_notifications_for_event) as mock_cancel:
            future_event.delete()
            mock_cancel.assert_called_once()

        call_command("send_reminders")
        self.assertEqual(len(mail.outbox), 0)


class NotificationSettingsUITestCase(TestCase):
    """
    Test suite verifying the /notifications/ settings UI, SMS disabled state,
    and canceling pending reminders when notifications are disabled.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="settingsuser",
            email="settings@example.com",
            password="testpassword123",
            phone_number="555-0144",
        )
        self.client.force_login(self.user)
        self.url = reverse("notifications:settings")
        self.now = timezone.now()

    def test_settings_page_displays_sms_as_unavailable_and_disabled(self):
        """
        The notification settings UI must clearly mark SMS reminders as unavailable/disabled
        while allowing email reminder configuration.
        """
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "notifications/settings.html")
        self.assertContains(response, "Unavailable (Email-Only)")
        self.assertContains(response, 'aria-disabled="true"')

    def test_disabling_notifications_cancels_pending_and_stops_future_queuing(self):
        """
        Disabling email notifications via the settings UI must cancel all existing pending
        NotificationQueue entries and prevent new events from queuing pending reminders.
        """
        future_event = Event.objects.create(
            user=self.user,
            title="Study Session",
            start_time=self.now + timedelta(hours=5),
            end_time=self.now + timedelta(hours=6),
        )
        self.assertEqual(
            NotificationQueue.objects.filter(event=future_event, status=NotificationQueue.Status.PENDING).count(),
            1,
        )

        # Disable email notifications via POST
        response = self.client.post(
            self.url,
            data={"email_enabled": "", "reminder_minutes": 60},
        )
        self.assertRedirects(response, self.url)

        pref = NotificationPreference.objects.get(user=self.user)
        self.assertFalse(pref.email_enabled)
        self.assertFalse(pref.sms_enabled)

        # Existing pending row must be marked canceled
        self.assertEqual(
            NotificationQueue.objects.filter(event=future_event, status=NotificationQueue.Status.CANCELED).count(),
            1,
        )
        self.assertEqual(
            NotificationQueue.objects.filter(event=future_event, status=NotificationQueue.Status.PENDING).count(),
            0,
        )

        # New events created while disabled must not queue pending reminders
        second_event = Event.objects.create(
            user=self.user,
            title="Disabled Event",
            start_time=self.now + timedelta(hours=6),
            end_time=self.now + timedelta(hours=7),
        )
        self.assertEqual(NotificationQueue.objects.filter(event=second_event).count(), 0)

        # Re-enabling with 30-minute lead time schedules reminders for future events
        self.client.post(
            self.url,
            data={"email_enabled": "on", "reminder_minutes": 30},
        )
        new_pending = NotificationQueue.objects.get(
            event=future_event,
            status=NotificationQueue.Status.PENDING,
        )
        self.assertEqual(new_pending.target_time, future_event.start_time - timedelta(minutes=30))

    def test_custom_manual_notification_email_used_for_sending(self):
        """
        Typing a custom email address in Notification Settings should save it
        and route sent reminders to that custom email instead of account email.
        """
        self.client.post(
            self.url,
            data={
                "email_enabled": "on",
                "notification_email": "custom_alerts@example.com",
                "reminder_minutes": 60,
            },
        )
        pref = NotificationPreference.objects.get(user=self.user)
        self.assertEqual(pref.notification_email, "custom_alerts@example.com")

        event = Event.objects.create(
            user=self.user,
            title="Custom Email Reminder Test",
            start_time=self.now + timedelta(hours=3),
            end_time=self.now + timedelta(hours=4),
        )
        notif = NotificationQueue.objects.get(event=event)
        notif.target_time = self.now - timedelta(minutes=1)
        notif.save()

        call_command("send_reminders")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["custom_alerts@example.com"])

    def test_send_test_email_button_dispatches_to_typed_email(self):
        """
        Clicking 'Send Test Email' on /notifications/ should immediately send
        a test email to the entered address (or account email if blank).
        """
        response = self.client.post(
            self.url,
            data={
                "action": "send_test",
                "email_enabled": "on",
                "notification_email": "personal_test@example.com",
                "reminder_minutes": 60,
            },
        )
        self.assertRedirects(response, self.url)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["personal_test@example.com"])
        self.assertIn("Heads Up Test Notification", mail.outbox[0].subject)
