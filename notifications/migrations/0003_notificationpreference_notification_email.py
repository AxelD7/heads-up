# Migration to add optional manual notification_email field to NotificationPreference.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0002_notificationpreference'),
    ]

    operations = [
        migrations.AddField(
            model_name='notificationpreference',
            name='notification_email',
            field=models.EmailField(blank=True, max_length=254),
        ),
    ]
