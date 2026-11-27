import logging
import os
import sys
import threading
from django.conf import settings
from django.db import close_old_connections

from .services import send_due_notifications

logger = logging.getLogger(__name__)

_scheduler_lock = threading.Lock()
_scheduler_started = False


def should_start_scheduler(argv=None, environ=None):
    """
    Only start the background reminder loop inside an active runserver process,
    avoiding extra threads during tests, migrations, management commands, or the autoreloader parent.
    """
    args = sys.argv if argv is None else argv
    env = os.environ if environ is None else environ

    command = next((arg for arg in args[1:] if not arg.startswith("-")), None)
    if command != "runserver":
        return False

    return env.get("RUN_MAIN") == "true" or "--noreload" in args


def run_pending_reminders_once():
    """
    Dispatch any due reminders safely and clean up stale database connections.
    """
    try:
        close_old_connections()
        send_due_notifications()
    except Exception:
        logger.exception("Unexpected error while checking scheduled event reminders.")
    finally:
        close_old_connections()


def _scheduler_loop(stop_event, poll_interval, initial_delay=3):
    """
    Periodically poll for due reminders until stop_event is signaled.
    """
    if stop_event.wait(initial_delay):
        return

    while not stop_event.is_set():
        run_pending_reminders_once()
        if stop_event.wait(poll_interval):
            break


def start_reminder_scheduler(stop_event=None):
    """
    Start a single daemon background thread for automatic reminders while runserver is running.
    """
    global _scheduler_started

    if not should_start_scheduler():
        return None

    with _scheduler_lock:
        if _scheduler_started:
            return None

        poll_interval = getattr(settings, "NOTIFICATION_POLL_INTERVAL_SECONDS", 15)
        event = stop_event or threading.Event()
        thread = threading.Thread(
            target=_scheduler_loop,
            args=(event, poll_interval),
            name="notification-reminder-scheduler",
            daemon=True,
        )
        thread.start()
        _scheduler_started = True
        return thread
