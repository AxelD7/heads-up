from django import forms
from .models import Event


class EventForm(forms.ModelForm):
    """
    Form for creating and updating events.
    """

    # internal start time does not need to respect user preference
    # instead we can impliment that on the front end to change display to users

    # Get and save the start time of the event  
    start_time = forms.DateTimeField(
        widget=forms.DateTimeInput(
        attrs={
            "type": "datetime-local",
            "class": "form-control",
        },
        format="%Y-%m-%dT%H:%M",
        ),
    )
    # Get and save the end time of the event
    end_time = forms.DateTimeField(
        widget=forms.DateTimeInput(
        attrs={
            "type": "datetime-local",
            "class": "form-control",
        },
        format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = Event
        fields = [
            "title",
            "start_time",
            "end_time",
            "location",
            "description",
            "category",
        ]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter event title",
            }),
            "location": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter event location",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Event description",
            }),
            "category": forms.Select(attrs={
                "class": "form-select",
            }),
        }

    # Utilizing django's in-built data cleaning for consistency of data
    def clean(self):
        cleaned_data = super().clean()

        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        # Validity Check that start time < end time & start time != end time plus error throwing 
        if start_time and end_time and end_time <= start_time:
            self.add_error(
                "end_time",
                "End time must be after start time."
            )

        return cleaned_data