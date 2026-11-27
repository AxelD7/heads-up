from django import forms
from .models import NotificationPreference


class NotificationPreferenceForm(forms.ModelForm):
    """
    Form allowing users to toggle email reminders and pick how early
    before an event they want to be notified. SMS is excluded (email-only).
    """
    class Meta:
        model = NotificationPreference
        fields = ["email_enabled", "notification_email", "reminder_minutes"]
        widgets = {
            "email_enabled": forms.CheckboxInput(attrs={
                "class": "form-check-input",
                "role": "switch",
            }),
            "notification_email": forms.EmailInput(attrs={
                "class": "form-control",
                "placeholder": "Optional: type a custom email (blank uses your account email)",
            }),
            "reminder_minutes": forms.Select(attrs={
                "class": "form-select",
            }),
        }
        labels = {
            "email_enabled": "Enable Email Reminders",
            "notification_email": "Reminder Email Address (Optional)",
            "reminder_minutes": "Notify Me Before Event",
        }
