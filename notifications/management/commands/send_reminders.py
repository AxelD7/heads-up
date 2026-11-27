from django.core.management.base import BaseCommand
from notifications.services import send_due_notifications


class Command(BaseCommand):
    """
    Management command (python manage.py send_reminders) that queries due pending
    NotificationQueue rows and dispatches email reminders.
    """
    help = "Process due NotificationQueue entries and send email reminders."

    def handle(self, *args, **options):
        self.stdout.write("Checking for due event reminders...")

        results = send_due_notifications()
        total = results["total"]
        sent = results["sent"]
        retrying = results["retrying"]
        failed = results["failed"]

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No pending reminders due right now."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Processed {total} due reminders: {sent} sent, {retrying} retrying, {failed} failed."
                )
            )
