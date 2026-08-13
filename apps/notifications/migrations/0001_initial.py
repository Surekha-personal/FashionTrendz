"""Initial schema for the notifications module.

Notification (one message to one person on one channel — simultaneously the
in-app inbox row and the delivery ledger) and NotificationPreference (one row
of opt-outs per customer).
"""

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('email_enabled', models.BooleanField(default=True, verbose_name='email')),
                ('sms_enabled', models.BooleanField(default=True, verbose_name='SMS')),
                ('push_enabled', models.BooleanField(default=True, verbose_name='push')),
                ('marketing_enabled', models.BooleanField(default=True, verbose_name='marketing')),
                ('push_token', models.CharField(blank=True, help_text='Device token registered by the frontend.', max_length=255, verbose_name='push token')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preference', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
            ],
            options={
                'verbose_name': 'notification preference',
                'verbose_name_plural': 'notification preferences',
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('event', models.CharField(db_index=True, help_text='Template key, e.g. order_shipped. See notifications/templates.py.', max_length=64, verbose_name='event')),
                ('category', models.CharField(choices=[('account', 'Account'), ('order', 'Order'), ('payment', 'Payment'), ('review', 'Review'), ('marketing', 'Marketing'), ('system', 'System')], db_index=True, default='system', max_length=16, verbose_name='category')),
                ('channel', models.CharField(choices=[('in_app', 'In-app'), ('email', 'Email'), ('sms', 'SMS'), ('push', 'Push')], db_index=True, default='in_app', max_length=8, verbose_name='channel')),
                ('subject', models.CharField(max_length=200, verbose_name='subject')),
                ('body', models.TextField(verbose_name='body')),
                ('link', models.CharField(blank=True, max_length=255, verbose_name='link')),
                ('context', models.JSONField(blank=True, default=dict, verbose_name='context')),
                ('status', models.CharField(choices=[('pending', 'Queued'), ('sent', 'Sent'), ('failed', 'Failed'), ('delivered', 'Delivered')], db_index=True, default='pending', max_length=12, verbose_name='status')),
                ('is_read', models.BooleanField(db_index=True, default=False, verbose_name='read')),
                ('read_at', models.DateTimeField(blank=True, null=True, verbose_name='read at')),
                ('sent_at', models.DateTimeField(blank=True, null=True, verbose_name='sent at')),
                ('attempts', models.PositiveSmallIntegerField(default=0, verbose_name='delivery attempts')),
                ('error', models.CharField(blank=True, max_length=255, verbose_name='last error')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notifications', to=settings.AUTH_USER_MODEL, verbose_name='recipient')),
            ],
            options={
                'verbose_name': 'notification',
                'verbose_name_plural': 'notifications',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', 'is_read', '-created_at'], name='notif_inbox_idx'), models.Index(fields=['status', 'channel'], name='notif_queue_idx'), models.Index(fields=['event', '-created_at'], name='notif_event_idx'), models.Index(fields=['user', 'event'], name='notif_dedupe_idx')],
            },
        ),
    ]
