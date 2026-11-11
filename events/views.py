from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import Event
from .forms import EventForm

# All functions require login from user to ensure security of events made by users

# Event views
@login_required()
def dashboard(request):
    
    context = {
        "message": "Hello from the dashboard"
    }
    
    return render(request, "dashboard.html", context)


@login_required
def event_list(request):
    """
    Display all events belonging to logged-in user.
    """
    # Pulls all events from the user's account and orders them via start time
    events = Event.objects.filter(
        user=request.user
    ).order_by("start_time")
    # Returns the event_list html placeholder until we get the front end
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
    # Searches for the event that matches the ID the user is requesting. This ensures no multiple name issues
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )
    # Returns the event_details html placeholder until we get the front end
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
        # Confirm form is filled in correctly with django's in built parsing and custom rules defined in forms.py
        if form.is_valid():
            event = form.save(commit=False)

            # Assign ownership server side.
            event.user = request.user
            event.save()
            # Once created redirects the user to the newly created event's details page, again placeholder HTML until we develop frontend
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
    # Get the event requested by user by searching unique event ID
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )

    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        # Check if form is valid using django in-built parser plus definitions in forms.py before saving it 
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
    # Get the event requested by user by searching unique event ID
    event = get_object_or_404(
        Event,
        pk=pk,
        user=request.user
    )

    event.delete()

    return redirect("events:event_list")
