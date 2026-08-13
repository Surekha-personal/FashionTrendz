"""Initial schema for the payments module.

Payment, PaymentAttempt, Refund and PaymentWebhookLog."""

import apps.payments.validators
import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orders', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('gateway', models.CharField(db_index=True, help_text='Registry key, e.g. razorpay or cod.', max_length=32, verbose_name='gateway')),
                ('method', models.CharField(blank=True, help_text='How the customer paid, as reported by the gateway.', max_length=32, verbose_name='method')),
                ('gateway_order_id', models.CharField(blank=True, db_index=True, max_length=100, validators=[django.core.validators.RegexValidator(code='invalid_gateway_id', message='Enter a valid gateway identifier.', regex='^[A-Za-z0-9_\\-]{6,100}$')], verbose_name='gateway order id')),
                ('gateway_payment_id', models.CharField(blank=True, db_index=True, max_length=100, validators=[django.core.validators.RegexValidator(code='invalid_gateway_id', message='Enter a valid gateway identifier.', regex='^[A-Za-z0-9_\\-]{6,100}$')], verbose_name='gateway payment id')),
                ('gateway_signature', models.CharField(blank=True, help_text='Kept for dispute evidence — it proves the callback was genuine.', max_length=255, verbose_name='gateway signature')),
                ('transaction_id', models.CharField(blank=True, db_index=True, max_length=100, verbose_name='transaction id')),
                ('reference_number', models.CharField(blank=True, help_text='Bank or UPI reference the customer sees on their statement.', max_length=64, verbose_name='reference number')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[apps.payments.validators.validate_positive_amount], verbose_name='amount')),
                ('refunded_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), editable=False, max_digits=12, verbose_name='refunded amount')),
                ('currency', models.CharField(default='INR', max_length=3, verbose_name='currency')),
                ('status', models.CharField(choices=[('created', 'Created'), ('authorised', 'Authorised'), ('captured', 'Captured'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('refunded', 'Refunded'), ('partially_refunded', 'Partially refunded')], db_index=True, default='created', max_length=24, verbose_name='status')),
                ('failure_reason', models.CharField(blank=True, max_length=255, verbose_name='failure reason')),
                ('captured_at', models.DateTimeField(blank=True, null=True, verbose_name='captured at')),
                ('raw_response', models.JSONField(blank=True, default=dict, help_text='Verbatim provider payload, for disputes and debugging.', verbose_name='raw gateway response')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='orders.order', verbose_name='order')),
            ],
            options={
                'verbose_name': 'payment',
                'verbose_name_plural': 'payments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PaymentAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('attempt_number', models.PositiveSmallIntegerField(default=1, verbose_name='attempt number')),
                ('status', models.CharField(choices=[('started', 'Started'), ('succeeded', 'Succeeded'), ('failed', 'Failed'), ('abandoned', 'Abandoned')], db_index=True, default='started', max_length=16, verbose_name='status')),
                ('failure_reason', models.CharField(blank=True, max_length=255, verbose_name='failure reason')),
                ('failure_code', models.CharField(blank=True, max_length=64, verbose_name='failure code')),
                ('retry_count', models.PositiveSmallIntegerField(default=0, verbose_name='retry count')),
                ('gateway_response', models.JSONField(blank=True, default=dict, verbose_name='gateway response')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attempts', to='payments.payment', verbose_name='payment')),
            ],
            options={
                'verbose_name': 'payment attempt',
                'verbose_name_plural': 'payment attempts',
                'ordering': ['payment', 'attempt_number'],
            },
        ),
        migrations.CreateModel(
            name='PaymentWebhookLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('gateway', models.CharField(db_index=True, max_length=32, verbose_name='gateway')),
                ('event_id', models.CharField(db_index=True, help_text="Provider's stable id for this event. The idempotency key.", max_length=200, verbose_name='event id')),
                ('event_type', models.CharField(db_index=True, max_length=64, verbose_name='event type')),
                ('signature', models.CharField(blank=True, max_length=255, verbose_name='signature')),
                ('is_verified', models.BooleanField(default=False, verbose_name='signature verified')),
                ('is_duplicate', models.BooleanField(db_index=True, default=False, help_text='The provider re-sent an event already processed.', verbose_name='duplicate')),
                ('payload', models.JSONField(blank=True, default=dict, verbose_name='payload')),
                ('headers', models.JSONField(blank=True, default=dict, verbose_name='headers')),
                ('processed_at', models.DateTimeField(blank=True, null=True, verbose_name='processed at')),
                ('error', models.TextField(blank=True, help_text='Stack summary when handling raised. Non-empty means unapplied.', verbose_name='processing error')),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='webhook_logs', to='payments.payment', verbose_name='payment')),
            ],
            options={
                'verbose_name': 'payment webhook log',
                'verbose_name_plural': 'payment webhook logs',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Refund',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12, validators=[apps.payments.validators.validate_positive_amount], verbose_name='refund amount')),
                ('currency', models.CharField(default='INR', max_length=3, verbose_name='currency')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('processed', 'Processed'), ('failed', 'Failed')], db_index=True, default='pending', max_length=16, verbose_name='status')),
                ('reason', models.CharField(choices=[('order_cancelled', 'Order cancelled'), ('order_returned', 'Order returned'), ('item_unavailable', 'Item unavailable'), ('damaged', 'Damaged on arrival'), ('goodwill', 'Goodwill gesture'), ('duplicate', 'Duplicate payment'), ('other', 'Other')], db_index=True, default='other', max_length=24, verbose_name='reason')),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='notes')),
                ('gateway_refund_id', models.CharField(blank=True, db_index=True, max_length=100, verbose_name='gateway refund id')),
                ('reference_number', models.CharField(blank=True, help_text='What the customer will see on their statement.', max_length=64, verbose_name='reference number')),
                ('processed_at', models.DateTimeField(blank=True, null=True, verbose_name='processed at')),
                ('raw_response', models.JSONField(blank=True, default=dict, verbose_name='raw gateway response')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='refunds', to='payments.payment', verbose_name='payment')),
            ],
            options={
                'verbose_name': 'refund',
                'verbose_name_plural': 'refunds',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['order', '-created_at'], name='payment_order_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['status', '-created_at'], name='payment_status_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['gateway', 'status'], name='payment_gateway_idx'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(condition=models.Q(('gateway_payment_id__gt', '')), fields=('gateway', 'gateway_payment_id'), name='unique_gateway_payment_id'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.UniqueConstraint(condition=models.Q(('gateway_order_id__gt', '')), fields=('gateway', 'gateway_order_id'), name='unique_gateway_order_id'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(condition=models.Q(('refunded_amount__lte', models.F('amount'))), name='payment_refund_within_amount'),
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', Decimal('0'))), name='payment_amount_positive'),
        ),
        migrations.AddIndex(
            model_name='paymentattempt',
            index=models.Index(fields=['payment', 'attempt_number'], name='attempt_payment_idx'),
        ),
        migrations.AddConstraint(
            model_name='paymentattempt',
            constraint=models.UniqueConstraint(fields=('payment', 'attempt_number'), name='unique_attempt_number_per_payment'),
        ),
        migrations.AddIndex(
            model_name='paymentwebhooklog',
            index=models.Index(fields=['gateway', 'event_type'], name='webhook_type_idx'),
        ),
        migrations.AddIndex(
            model_name='paymentwebhooklog',
            index=models.Index(fields=['-created_at'], name='webhook_recent_idx'),
        ),
        migrations.AddConstraint(
            model_name='paymentwebhooklog',
            constraint=models.UniqueConstraint(fields=('gateway', 'event_id'), name='unique_webhook_event'),
        ),
        migrations.AddIndex(
            model_name='refund',
            index=models.Index(fields=['payment', '-created_at'], name='refund_payment_idx'),
        ),
        migrations.AddIndex(
            model_name='refund',
            index=models.Index(fields=['status', '-created_at'], name='refund_status_idx'),
        ),
        migrations.AddConstraint(
            model_name='refund',
            constraint=models.UniqueConstraint(condition=models.Q(('gateway_refund_id__gt', '')), fields=('gateway_refund_id',), name='unique_gateway_refund_id'),
        ),
        migrations.AddConstraint(
            model_name='refund',
            constraint=models.CheckConstraint(condition=models.Q(('amount__gt', Decimal('0'))), name='refund_amount_positive'),
        ),
    ]
