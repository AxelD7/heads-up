import re

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import CustomUser

# An optional leading +, then digits with optional spaces, dashes, dots or brackets between them.
PHONE_ALLOWED_CHARS = re.compile(r"\+?[\d\s().-]+")


class SignUpForm(UserCreationForm):
    """
    Form used on the sign up (account creation) page.

    UserCreationForm already handles the username, the two password boxes,
    checking that the passwords match and running the password rules from
    AUTH_PASSWORD_VALIDATORS in settings.py. We add the extra fields our
    CustomUser model has, plus a few checks so people get a clear message
    instead of a database error.
    """

    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        help_text="Used for text reminders. Digits only, or with spaces, dashes, dots, brackets or a leading +.",
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
    )
    date_format = forms.ChoiceField(
        label="Date format",
        choices=CustomUser.DATE_FORMAT_CHOICES,
        initial="M/D/Y",
    )
    time_format = forms.ChoiceField(
        label="Time format",
        choices=CustomUser.TIME_FORMAT_CHOICES,
        initial="12h",
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_format",
            "time_format",
        )

    # Note: UserCreationForm already rejects usernames that only differ in case
    # (e.g. "Jacob" when "jacob" exists), so we don't need our own check for that.

    def clean_email(self):
        # Emails are unique on the model, so give a friendly error instead of a crash.
        email = self.cleaned_data["email"].strip().lower()
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data["phone_number"].strip()
        if not PHONE_ALLOWED_CHARS.fullmatch(phone):
            raise forms.ValidationError(
                "Phone numbers can only contain digits, spaces, dashes, dots, brackets and a leading +."
            )
        digit_count = sum(ch.isdigit() for ch in phone)
        if not 7 <= digit_count <= 15:
            raise forms.ValidationError("Enter a phone number with 7 to 15 digits.")
        return phone


class LoginForm(AuthenticationForm):
    """
    Form used on the log in page. Same as Django's built-in one, but the
    username box says it also accepts an email (see users/backends.py).
    """

    username = forms.CharField(
        label="Username or email",
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"}),
    )
