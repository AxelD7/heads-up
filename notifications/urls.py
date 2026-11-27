from django.urls import path
from . import views

app_name = "notifications"

urlpatterns = [
    # Notification settings & reminder history page (/notifications/)
    path("", views.notification_settings, name="settings"),
]
