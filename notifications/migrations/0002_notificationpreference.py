# Migration to create the NotificationPreference table for per-user reminder settings.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email_enabled', models.BooleanField(default=True)),
                ('reminder_minutes', models.PositiveIntegerField(choices=[(15, '15 minutes before'), (30, '30 minutes before'), (60, '1 hour before'), (1440, '1 day before')], default=60)),
                ('sms_enabled', models.BooleanField(default=False)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preference', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
