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
        input_formats=["%Y-%m-%dT%H:%M"],
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
        input_formats=["%Y-%m-%dT%H:%M"],
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


class CalendarImportForm(forms.Form):
    """
    Form allowing users to import events by pasting a Moodle/Google .ics URL
    or uploading a downloaded .ics file from their device.
    """
    SOURCE_CHOICES = [
        ("Moodle", "Moodle"),
        ("Google", "Google Calendar"),
        ("OUSail", "OUSail"),
    ]

    source_type = forms.ChoiceField(
        choices=SOURCE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Calendar Source",
    )
    feed_url = forms.URLField(
        required=False,
        max_length=500,
        widget=forms.URLInput(attrs={
            "class": "form-control",
            "placeholder": "https://calendar.google.com/calendar/ical/... or Moodle export URL",
        }),
        label="iCal (.ics) Feed URL",
    )
    ics_file = forms.FileField(
        required=False,
        widget=forms.ClearableFileInput(attrs={
            "class": "form-control",
            "accept": ".ics,text/calendar",
        }),
        label="Or Upload a .ics File",
    )
    category = forms.ChoiceField(
        choices=Event.Category.choices,
        initial=Event.Category.ACADEMIC,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Default Category",
    )

    def clean_feed_url(self):
        """
        Convert webcal:// links into https:// so Python can fetch them cleanly.
        """
        url = self.cleaned_data.get("feed_url", "").strip()
        if url.startswith("webcal://"):
            url = "https://" + url[len("webcal://"):]
        return url

    def clean(self):
        """
        Ensure the user provided either a feed URL or an uploaded .ics file.
        """
        cleaned_data = super().clean()
        feed_url = cleaned_data.get("feed_url")
        ics_file = cleaned_data.get("ics_file")

        if not feed_url and not ics_file:
            raise forms.ValidationError(
                "Please enter an iCal (.ics) feed URL or upload a .ics file."
            )

        return cleaned_data