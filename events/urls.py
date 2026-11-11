from django.urls import path

from . import views


app_name = "events"

urlpatterns = [
    # Default view
    path("", views.dashboard, name="dashboard"),
    
    #Path to view list a currently logged in user of events
    path("/list", views.event_list, name="event_list"),

    # Path when creating a event
    path("create/", views.event_create, name="event_create"),

    # Path when selecting to view a event
    path("<int:pk>/", views.event_detail, name="event_detail"),

    # Path when updating a event
    path("<int:pk>/update/", views.event_update, name="event_update"),

    # Path when deleting a event
    path("<int:pk>/delete/", views.event_delete, name="event_delete"),
]
