from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Event
from .forms import EventForm


@login_required
def event_list(request):
    """
    Display all events belonging to logged-in user.
    """
    events = Event.objects.filter(
        user=request.user
    ).order_by("start_time")

    return render(
        request,
        "events/event_list.html",
        {"events": events}
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