from django.urls import path

from . import views


app_name = "events"

urlpatterns = [

    
    #Path to view dashboard contianing a list of the currently logged in user of events
    path("", views.event_list, name="event_list"),

    # Path when creating a event
    path("create/", views.event_create, name="event_create"),

    # Path when selecting to view a event
    path("<int:pk>/", views.event_detail, name="event_detail"),

    # Path when updating a event
    path("<int:pk>/update/", views.event_update, name="event_update"),

    # Path to confirm an event deletion
    path("<int:pk>/delete/confirm/", views.event_delete_confirm, name="event_delete_confirm"),

    # Path when deleting a event
    path("<int:pk>/delete/", views.event_delete, name="event_delete"),
]
