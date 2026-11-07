# Migration to create the initial database tables for the events app.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    # Indicates this is the first migration for the events app
    initial = True

    # Depends on the CustomUser model being available
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: Create the table for external calendar feeds (Google, Moodle, etc.)
        migrations.CreateModel(
            name='ExternalFeed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_type', models.CharField(max_length=50)),
                ('feed_url', models.URLField(blank=True, max_length=500)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='external_feeds', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        # Step 2: Create the table for calendar events
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('location', models.CharField(blank=True, max_length=200)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(choices=[('academic', 'Academic'), ('personal', 'Personal'), ('work', 'Work')], default='personal', max_length=20)),
                ('is_imported', models.BooleanField(default=False)),
                ('external_id', models.CharField(blank=True, max_length=255)),
                ('content_hash', models.CharField(blank=True, max_length=64)),
                ('feed', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='events', to='events.externalfeed')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['start_time'],
            },
        ),
        # Step 3: Prevent duplicate imported events from the same feed with the same external ID
        migrations.AddConstraint(
            model_name='event',
            constraint=models.UniqueConstraint(condition=models.Q(('external_id', ''), _negated=True), fields=('feed', 'external_id'), name='unique_feed_external_id'),
        ),
    ]
