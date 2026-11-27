# Migration to add 1, 2, 5, and 10 minute reminder lead-time choices.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_notificationpreference_notification_email'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notificationpreference',
            name='reminder_minutes',
            field=models.PositiveIntegerField(choices=[(1, '1 minute before'), (2, '2 minutes before'), (5, '5 minutes before'), (10, '10 minutes before'), (15, '15 minutes before'), (30, '30 minutes before'), (60, '1 hour before'), (1440, '1 day before')], default=60),
        ),
    ]
