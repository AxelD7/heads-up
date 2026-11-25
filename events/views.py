import secrets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Event, ExternalFeed
from .forms import CalendarImportForm, EventForm
from .google_calendar import (
    GOOGLE_CALENDAR_EVENTS_URL,
    build_google_auth_url,
    exchange_code_for_tokens,
    sync_google_events,
)
from .services import fetch_ics_from_url, sync_ics_events


# Event views
@login_required
def event_list(request):
    """
    Display the interactive calendar dashboard for the logged-in user.
    Supports optional '?source=Moodle' or '?source=Google' filtering.
    """
    active_source = request.GET.get("source", "").strip()
    events = (
        Event.objects.filter(user=request.user)
        .select_related("feed")
        .order_by("start_time")
    )

    if active_source:
        events = events.filter(feed__source_type__iexact=active_source)

    # Category color palette matching Heads Up UI styling
    category_colors = {
        Event.Category.ACADEMIC: "#2b6cb0",
        Event.Category.PERSONAL: "#38a169",
        Event.Category.WORK: "#dd6b20",
    }

    # Build JSON-ready list for FullCalendar.js
    calendar_events = []
    for event in events:
        source_label = event.feed.source_type if event.feed else "Manual"
        calendar_events.append({
            "id": event.pk,
            "title": event.title,
            "start": event.start_time.isoformat(),
            "end": event.end_time.isoformat(),
            "url": reverse("events:event_detail", kwargs={"pk": event.pk}),
            "backgroundColor": category_colors.get(event.category, "#2b6cb0"),
            "borderColor": category_colors.get(event.category, "#2b6cb0"),
            "extendedProps": {
                "category": event.get_category_display(),
                "location": event.location,
                "source": source_label,
            },
        })

    # Upcoming events list for the sidebar card (next 5 events)
    upcoming_events = events.filter(end_time__gte=timezone.now())[:5]
    user_feeds = ExternalFeed.objects.filter(user=request.user).order_by("source_type")
    use_24h = getattr(request.user, "time_format", "12h") == "24h"

    return render(
        request,
        "events/dashboard.html",
        {
            "events": events,
            "calendar_events": calendar_events,
            "upcoming_events": upcoming_events,
            "active_source": active_source,
            "user_feeds": user_feeds,
            "use_24h": use_24h,
        },
    )

@login_required
def event_detail(request, pk):
    """
    Display details of a specific event owned by the logged-in user.
    """
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        "events/event_detail.html",
        {"event": event}
    )


@login_required
def event_create(request):
    """
    Create a new event for the logged-in user.
    """
    if request.method == "POST":
        form = EventForm(request.POST)

        if form.is_valid():
            event = form.save(commit=False)

            # Assign ownership server side.
            event.user = request.user
            event.save()

            return redirect("events:event_detail", pk=event.pk)

    else:
        form = EventForm()

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "action": "Create",
        }
    )


@login_required
def event_update(request, pk):
    """
    Update an existing event belonging to the logged-in user.
    """
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)

        if form.is_valid():
            form.save()

            return redirect("events:event_detail", pk=event.pk)

    else:
        form = EventForm(instance=event)

    return render(
        request,
        "events/event_form.html",
        {
            "form": form,
            "event": event,
            "action": "Update",
        }
    )


@login_required
@require_POST #Stops visiting delete url directly by user to prevent accidental deletion
def event_delete(request, pk):
    """
    Delete an existing event belonging to the logged-in user.
    """
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )
    event.delete()

    return redirect("events:event_list")
    

@login_required
@require_GET
def event_delete_confirm(request, pk):
    """
    Display a confirmation page before deleting an event.
    """
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )

    return render(
        request,
        "events/event_confirm_delete.html",
        {"event": event}
    )


@login_required
def import_calendar(request):
    """
    Allow users to import external calendars (Moodle, Google, OUSail)
    by pasting an iCal (.ics) feed URL or uploading a .ics file.
    """
    user_feeds = ExternalFeed.objects.filter(user=request.user).order_by("source_type")

    if request.method == "POST":
        form = CalendarImportForm(request.POST, request.FILES)
        if form.is_valid():
            source_type = form.cleaned_data["source_type"]
            feed_url = form.cleaned_data["feed_url"]
            ics_file = form.cleaned_data["ics_file"]
            category = form.cleaned_data["category"]

            try:
                if ics_file:
                    ics_content = ics_file.read().decode("utf-8", errors="replace")
                    if "BEGIN:VCALENDAR" not in ics_content.upper():
                        raise ValueError("The uploaded file is not a valid iCalendar (.ics) file.")
                else:
                    ics_content = fetch_ics_from_url(feed_url)

                # Reuse existing feed for the same URL or create a new ExternalFeed record
                feed = None
                if feed_url:
                    feed, _ = ExternalFeed.objects.get_or_create(
                        user=request.user,
                        source_type=source_type,
                        feed_url=feed_url,
                    )
                else:
                    feed = ExternalFeed.objects.create(
                        user=request.user,
                        source_type=source_type,
                        feed_url="",
                    )

                summary = sync_ics_events(
                    user=request.user,
                    ics_content=ics_content,
                    feed=feed,
                    category=category,
                )
                messages.success(
                    request,
                    f"{source_type} sync complete: {summary['created']} added, "
                    f"{summary['updated']} updated, {summary['skipped']} unchanged.",
                )
                return redirect(f"{reverse('events:event_list')}?source={source_type}")
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        initial_source = request.GET.get("source", "Moodle")
        form = CalendarImportForm(initial={"source_type": initial_source})

    return render(
        request,
        "events/import_calendar.html",
        {
            "form": form,
            "user_feeds": user_feeds,
        },
    )


@login_required
@require_POST
def sync_feed(request, pk):
    """
    Re-fetch and synchronize an existing ExternalFeed owned by the logged-in user.
    Supports both iCal (.ics) feeds and Google Calendar API feeds.
    """
    feed = get_object_or_404(ExternalFeed, pk=pk, user=request.user)
    if not feed.feed_url:
        messages.error(request, f"{feed.source_type} feed was uploaded from a file and has no URL to re-sync.")
        return redirect("events:event_list")

    # Handle Google Calendar API feeds using the session access token
    if feed.feed_url == GOOGLE_CALENDAR_EVENTS_URL:
        access_token = request.session.get("google_access_token")
        if not access_token:
            return redirect("events:google_connect")
        try:
            summary = sync_google_events(user=request.user, access_token=access_token, feed=feed)
            messages.success(
                request,
                f"Synced Google Calendar API: {summary['created']} added, "
                f"{summary['updated']} updated, {summary['skipped']} unchanged.",
            )
            return redirect(f"{reverse('events:event_list')}?source=Google")
        except ValueError:
            request.session.pop("google_access_token", None)
            return redirect("events:google_connect")

    try:
        ics_content = fetch_ics_from_url(feed.feed_url)
        summary = sync_ics_events(user=request.user, ics_content=ics_content, feed=feed)
        messages.success(
            request,
            f"Synced {feed.source_type}: {summary['created']} added, "
            f"{summary['updated']} updated, {summary['skipped']} unchanged.",
        )
    except ValueError as exc:
        messages.error(request, f"Sync failed for {feed.source_type}: {exc}")

    return redirect(f"{reverse('events:event_list')}?source={feed.source_type}")


@login_required
@require_POST
def delete_feed(request, pk):
    """
    Remove a connected ExternalFeed (and its imported events) owned by the logged-in user.
    """
    feed = get_object_or_404(ExternalFeed, pk=pk, user=request.user)
    source_name = feed.source_type
    feed.delete()
    messages.info(request, f"Removed {source_name} calendar feed and its imported events.")
    return redirect("events:event_list")


@login_required
def google_connect(request):
    """
    Start the Google OAuth 2.0 flow to grant read-only access to the user's Google Calendar.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        messages.error(
            request,
            "Google Calendar API credentials are not configured in .env yet.",
        )
        return redirect("events:import_calendar")

    # Store a random state token in the session to protect against CSRF attacks
    state = secrets.token_urlsafe(32)
    request.session["google_oauth_state"] = state
    return redirect(build_google_auth_url(state))


@login_required
def google_callback(request):
    """
    Receive Google's OAuth 2.0 callback, verify state, exchange the code for an access token,
    and import the user's Google Calendar events into HeadsUp.
    """
    error = request.GET.get("error")
    if error:
        messages.error(request, f"Google authorization canceled or failed: {error}")
        return redirect("events:import_calendar")

    expected_state = request.session.pop("google_oauth_state", None)
    returned_state = request.GET.get("state")
    if not expected_state or expected_state != returned_state:
        messages.error(request, "Invalid OAuth state. Please try connecting Google Calendar again.")
        return redirect("events:import_calendar")

    code = request.GET.get("code")
    if not code:
        messages.error(request, "Missing authorization code from Google.")
        return redirect("events:import_calendar")

    try:
        tokens = exchange_code_for_tokens(code)
        access_token = tokens["access_token"]
        request.session["google_access_token"] = access_token

        summary = sync_google_events(user=request.user, access_token=access_token)
        messages.success(
            request,
            f"Google Calendar synced: {summary['created']} added, "
            f"{summary['updated']} updated, {summary['skipped']} unchanged.",
        )
        return redirect(f"{reverse('events:event_list')}?source=Google")
    except ValueError as exc:
        messages.error(request, f"Google Calendar sync failed: {exc}")
        return redirect("events:import_calendar")
