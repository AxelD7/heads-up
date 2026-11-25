from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Event
from .forms import EventForm


# Event views
@login_required
def event_list(request):
    """
    Render the calendar dashboard with this user's events and preferences.
    """
    events = Event.objects.filter(user=request.user).order_by("start_time")
    # Stores list of events that are after the current time to use in the front end.
    upcoming_events = events.filter(start_time__gte=timezone.now())
    # Build the JSON dashboard event data that the front end needs for the calendar.
    dashboard_events = []
    for event in events:
        dashboard_events.append({
            "id": event.pk,
            "title": event.title,
            "category": event.category,
            "category_label": event.get_category_display(),
            # Milliseconds preserve the UTC instant and let the browser render it in local time.
            "start": int(event.start_time.timestamp() * 1000),
            "end": int(event.end_time.timestamp() * 1000),
            "location": event.location,
            "description": event.description,
            "detail_url": reverse("events:event_detail", kwargs={"pk": event.pk}),
        })

    return render(
        request,
        "events/dashboard.html",
        # Data being served to the template.
        {
            "events": upcoming_events,
            "dashboard_events": dashboard_events,
            # These preferences let the template and client-side calendar format dates consistently.
            "date_format": request.user.date_format,
            "time_format": request.user.time_format,
            "date_fmt": "j/n/Y" if request.user.date_format == "D/M/Y" else "n/j/Y",
            "time_fmt": "H:i" if request.user.time_format == "24h" else "g:i A",
            "event_categories": Event.Category.choices,
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

            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({
                    "id": event.pk,
                    "title": event.title,
                    "start": event.start_time.isoformat(),
                    "end": event.end_time.isoformat(),
                    "url": reverse("events:event_detail", kwargs={"pk": event.pk}),
                    "category": event.category,
                })

            return redirect("events:event_detail", pk=event.pk)

    else:
        form = EventForm()

    if (
        request.method == "POST"
        and request.headers.get("x-requested-with") == "XMLHttpRequest"
    ):
        return JsonResponse(
            {
                "errors": {
                    field: [str(error) for error in errors]
                    for field, errors in form.errors.items()
                }
            },
            status=400,
        )

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
