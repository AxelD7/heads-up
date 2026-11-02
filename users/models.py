from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=20)

    DATE_FORMAT_CHOICES = [
        ('M/D/Y', 'MM/DD/YYYY (e.g., 12/31/2026)'),
        ('D/M/Y', 'DD/MM/YYYY (e.g., 31/12/2026)'),
    ]

    TIME_FORMAT_CHOICES = [
        ('12h', '12-hour (e.g., 2:30 PM)'),
        ('24h', '24-hour (e.g., 14:30)'),
    ]

    date_format = models.CharField(
        max_length=10,
        choices=DATE_FORMAT_CHOICES,
        default='M/D/Y',
        help_text='Preferred date display format',
    )
    time_format = models.CharField(
        max_length=10,
        choices=TIME_FORMAT_CHOICES,
        default='12h',
        help_text='Preferred time display format',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.username
