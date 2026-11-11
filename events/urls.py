from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
    # Default view
    path("", views.event_list, name="event_list"),
    # Path when creating a event
    path("events/create/", views.event_create, name="event_create"),
    # Path when selecting to view a event
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    # Path when updating a event
    path("events/<int:pk>/update/", views.event_update, name="event_update"),
    # Path when deleting a event
    path("events/<int:pk>/delete/", views.event_delete, name="event_delete"),
]