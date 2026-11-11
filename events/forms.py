from django import forms
from .models import Event


class EventForm(forms.ModelForm):
    """
    Form for creating and updating events.
    """

    # internal start time does not need to respect user preference
    # instead we can impliment that on the front end to change display to users  
    start_time = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    end_time = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
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

    def clean(self):
        cleaned_data = super().clean()

        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        # Validity Check of start and end time plus error throwing 
        if start_time and end_time and end_time <= start_time:
            self.add_error(
                "end_time",
                "End time must be after start time."
            )

        return cleaned_data