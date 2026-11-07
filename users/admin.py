from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

# Register your models here.


class CustomUserAdmin(UserAdmin):
    # Columns for when viewing table of users.
    list_display = ["username", "first_name", "last_name", "email", "phone_number"]

    # Fieldset that appears when EDITING a user entity.
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "email",
                    "password",
                    "first_name",
                    "last_name",
                    "date_format",
                    "time_format",
                    "phone_number",
                ),
            },
        ),
    )
    
    # Fieldset that appears when creating a new user entity.
    add_fieldsets = (
            (
                None,
                {
                    "fields": (
                        "username",
                        "email",
                        "password1",
                        "password2",
                        "first_name",
                        "last_name",
                        "phone_number",
                    ),
                },
            ),
        )


admin.site.register(CustomUser, CustomUserAdmin)
