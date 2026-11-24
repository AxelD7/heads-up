from django.core.management.base import BaseCommand
from notifications.services import send_due_notifications


class Command(BaseCommand):
    """
    Management command to dispatch due calendar reminders.
    Can be run manually via terminal or scheduled periodically via Celery Beat or cron.
    """
    help = "Checks NotificationQueue for due email reminders and dispatches them via SMTP."

    def handle(self, *args, **options):
        self.stdout.write("Checking for due calendar notifications...")
        
        results = send_due_notifications()
        total = results["total"]
        sent = results["sent"]
        retrying = results["retrying"]
        failed = results["failed"]

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No reminders due at this time."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Completed notification dispatch: {sent} sent, {retrying} retrying, {failed} failed (out of {total} due)."
                )
            )
