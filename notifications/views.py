from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone

from events.models import Event
from .forms import NotificationPreferenceForm
from .models import NotificationPreference, NotificationQueue
from .services import cancel_user_pending_notifications, queue_notifications_for_event


@login_required
def notification_settings(request):
    """
    Display and update the logged-in user's notification preferences (email-only)
    and show their recent/scheduled reminders.
    Disabling email notifications immediately marks pending reminders as canceled.
    """
    pref, _ = NotificationPreference.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = NotificationPreferenceForm(request.POST, instance=pref)
        if form.is_valid():
            if request.POST.get("action") == "send_test":
                typed_email = form.cleaned_data.get("notification_email", "").strip()
                if typed_email and typed_email != pref.notification_email:
                    pref.notification_email = typed_email
                    pref.save(update_fields=["notification_email"])

                recipient = typed_email or pref.notification_email or request.user.email
                if not recipient:
                    messages.error(request, "Please type an email address first to send a test email.")
                    return redirect("notifications:settings")

                try:
                    send_mail(
                        subject="Heads Up Test Notification",
                        message=(
                            f"Hi {request.user.username},\n\n"
                            "This is a quick test notification from your Heads Up calendar app.\n"
                            "If you are reading this in your inbox, your email reminders are working!\n\n"
                            "— The Heads Up Calendar Team"
                        ),
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "headsup475@gmail.com"),
                        recipient_list=[recipient],
                        fail_silently=False,
                    )
                    messages.success(request, f"Test email sent to {recipient}! Check your inbox.")
                except Exception as exc:
                    messages.error(request, f"Could not send test email to {recipient}: {exc}")

                return redirect("notifications:settings")

            updated_pref = form.save(commit=False)
            # SMS remains unavailable/disabled (email-only)
            updated_pref.sms_enabled = False
            updated_pref.save()

            if not updated_pref.email_enabled:
                canceled_count = cancel_user_pending_notifications(request.user)
                messages.info(
                    request,
                    f"Email notifications disabled. {canceled_count} pending reminder(s) marked as canceled.",
                )
            else:
                # Reschedule upcoming events using the updated lead-time preference
                future_events = Event.objects.filter(
                    user=request.user,
                    start_time__gt=timezone.now(),
                )
                for event in future_events:
                    queue_notifications_for_event(event)
                messages.success(request, "Email notification settings saved.")

            return redirect("notifications:settings")
    else:
        form = NotificationPreferenceForm(instance=pref)

    recent_notifications = (
        NotificationQueue.objects.filter(user=request.user)
        .select_related("event")
        .order_by("-target_time")[:20]
    )

    return render(
        request,
        "notifications/settings.html",
        {
            "form": form,
            "preference": pref,
            "recent_notifications": recent_notifications,
        },
    )
