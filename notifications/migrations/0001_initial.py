# Migration to create the initial database tables for the notifications app.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    # Indicates this is the first migration for the notifications app
    initial = True

    # Depends on both the events app and the user model being available
    dependencies = [
        ('events', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Create the NotificationQueue table to store scheduled reminders
        migrations.CreateModel(
            name='NotificationQueue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('target_time', models.DateTimeField()),
                ('delivery_method', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS')], max_length=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('sent', 'Sent'), ('failed', 'Failed'), ('canceled', 'Canceled')], default='pending', max_length=20)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to='events.event')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['target_time'],
            },
        ),
        # Step 2: Add an index on (status, target_time) for fast querying of pending reminders
        migrations.AddIndex(
            model_name='notificationqueue',
            index=models.Index(fields=['status', 'target_time'], name='notif_status_target_idx'),
        ),
    ]
