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

    # Paths for importing and managing external Moodle / Google iCal feeds
    path("import/", views.import_calendar, name="import_calendar"),
    path("feeds/<int:pk>/sync/", views.sync_feed, name="sync_feed"),
    path("feeds/<int:pk>/delete/", views.delete_feed, name="delete_feed"),

    # Google Calendar API (OAuth 2.0) routes
    path("google/connect/", views.google_connect, name="google_connect"),
    path("google/callback/", views.google_callback, name="google_callback"),
]
