from django.urls import path
from . import views

app_name = "events"

urlpatterns = [
  
    path("", views.dashboard, name="dashboard"),

    path("create/", views.event_create, name="event_create"),

    path("<int:pk>/", views.event_detail, name="event_detail"),

    path("<int:pk>/update/", views.event_update, name="event_update"),

    path("<int:pk>/delete/", views.event_delete, name="event_delete"),

    path("<int:pk>/delete/confirm/", views.event_delete_confirm, name="event_delete_confirm"),

]
