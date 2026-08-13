"""Initial schema for the orders module.

Order, OrderItem, OrderStatusHistory and Shipment.
"""

import apps.orders.validators
import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('products', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('order_number', models.CharField(db_index=True, max_length=32, unique=True, validators=[django.core.validators.RegexValidator(code='invalid_order_number', message='Enter a valid order number, e.g. FT-ORD-20260804-7QK2M9.', regex='^FT-ORD-\\d{8}-[A-Z0-9]{6}$')], verbose_name='order number')),
                ('invoice_number', models.CharField(blank=True, db_index=True, help_text='Assigned when the invoice is first generated.', max_length=32, validators=[django.core.validators.RegexValidator(code='invalid_invoice_number', message='Enter a valid invoice number, e.g. FT-INV-202608-3XP7K2.', regex='^FT-INV-\\d{6}-[A-Z0-9]{6}$')], verbose_name='invoice number')),
                ('invoice_file', models.FileField(blank=True, null=True, upload_to='invoices/%Y/%m/', verbose_name='invoice PDF')),
                ('shipping_address', models.JSONField(help_text='Frozen copy of the delivery address as it was at checkout.', validators=[apps.orders.validators.validate_address_snapshot], verbose_name='shipping address')),
                ('billing_address', models.JSONField(help_text='Frozen copy of the billing address as it was at checkout.', validators=[apps.orders.validators.validate_address_snapshot], verbose_name='billing address')),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='subtotal')),
                ('discount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='discount')),
                ('coupon_code', models.CharField(blank=True, max_length=40, verbose_name='coupon code')),
                ('coupon_discount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='coupon discount')),
                ('shipping_charge', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='shipping charge')),
                ('platform_fee', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='platform fee')),
                ('tax', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='GST')),
                ('grand_total', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='grand total')),
                ('currency', models.CharField(choices=[('INR', 'Indian Rupee'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'Pound Sterling'), ('AED', 'UAE Dirham')], default='INR', max_length=3, verbose_name='currency')),
                ('payment_method', models.CharField(choices=[('card', 'Credit / debit card'), ('upi', 'UPI'), ('net_banking', 'Net banking'), ('wallet', 'Wallet'), ('cod', 'Cash on delivery')], default='cod', max_length=16, verbose_name='payment method')),
                ('payment_status', models.CharField(choices=[('pending', 'Pending'), ('authorised', 'Authorised'), ('paid', 'Paid'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('partially_refunded', 'Partially refunded'), ('refunded', 'Refunded')], db_index=True, default='pending', max_length=20, verbose_name='payment status')),
                ('payment_reference', models.CharField(blank=True, help_text='Gateway transaction id. Populated by the payments module.', max_length=100, verbose_name='payment reference')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('processing', 'Processing'), ('packed', 'Packed'), ('shipped', 'Shipped'), ('out_for_delivery', 'Out for delivery'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'), ('returned', 'Returned'), ('refunded', 'Refunded')], db_index=True, default='pending', max_length=20, verbose_name='order status')),
                ('delivery_status', models.CharField(choices=[('not_dispatched', 'Not dispatched'), ('dispatched', 'Dispatched'), ('in_transit', 'In transit'), ('out_for_delivery', 'Out for delivery'), ('delivered', 'Delivered'), ('failed', 'Delivery failed'), ('rto', 'Returned to origin')], db_index=True, default='not_dispatched', max_length=20, verbose_name='delivery status')),
                ('delivery_method', models.CharField(choices=[('standard', 'Standard delivery'), ('express', 'Express delivery'), ('scheduled', 'Scheduled delivery')], default='standard', max_length=16, verbose_name='delivery method')),
                ('estimated_delivery_date', models.DateField(blank=True, null=True, verbose_name='estimated delivery')),
                ('delivered_at', models.DateTimeField(blank=True, null=True, verbose_name='delivered at')),
                ('cancelled_at', models.DateTimeField(blank=True, null=True, verbose_name='cancelled at')),
                ('cancel_reason', models.CharField(blank=True, max_length=255, verbose_name='cancel reason')),
                ('notes', models.TextField(blank=True, help_text='Delivery instructions from the customer.', verbose_name='notes')),
                ('internal_notes', models.TextField(blank=True, help_text='Staff-only. Never shown to the customer.', verbose_name='internal notes')),
                ('stock_committed', models.BooleanField(default=False, editable=False, help_text='True once on-hand stock has been decremented. Decides whether a cancellation releases a reservation or puts units back on the shelf.', verbose_name='stock committed')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='orders', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
            ],
            options={
                'verbose_name': 'order',
                'verbose_name_plural': 'orders',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('product_name', models.CharField(max_length=200, verbose_name='product name')),
                ('product_slug', models.SlugField(blank=True, max_length=255, verbose_name='product slug')),
                ('brand_name', models.CharField(blank=True, max_length=120, verbose_name='brand')),
                ('sku', models.CharField(max_length=50, verbose_name='SKU')),
                ('size', models.CharField(blank=True, max_length=16, verbose_name='size')),
                ('color', models.CharField(blank=True, max_length=40, verbose_name='colour')),
                ('image_url', models.CharField(blank=True, max_length=500, verbose_name='image URL')),
                ('mrp', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='MRP')),
                ('selling_price', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='selling price')),
                ('discount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='discount')),
                ('tax', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='tax')),
                ('quantity', models.PositiveSmallIntegerField(verbose_name='quantity')),
                ('subtotal', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='subtotal')),
                ('grand_total', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='line total')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.order', verbose_name='order')),
                ('product', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_items', to='products.product', verbose_name='product')),
                ('variant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_items', to='products.productvariant', verbose_name='variant')),
            ],
            options={
                'verbose_name': 'order item',
                'verbose_name_plural': 'order items',
                'ordering': ['id'],
            },
        ),
        migrations.CreateModel(
            name='OrderStatusHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('previous_status', models.CharField(blank=True, choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('processing', 'Processing'), ('packed', 'Packed'), ('shipped', 'Shipped'), ('out_for_delivery', 'Out for delivery'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'), ('returned', 'Returned'), ('refunded', 'Refunded')], max_length=20, verbose_name='previous status')),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('confirmed', 'Confirmed'), ('processing', 'Processing'), ('packed', 'Packed'), ('shipped', 'Shipped'), ('out_for_delivery', 'Out for delivery'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled'), ('returned', 'Returned'), ('refunded', 'Refunded')], max_length=20, verbose_name='status')),
                ('remarks', models.CharField(blank=True, max_length=255, verbose_name='remarks')),
                ('changed_by', models.ForeignKey(blank=True, help_text='Null for automated transitions.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='order_status_changes', to=settings.AUTH_USER_MODEL, verbose_name='changed by')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='status_history', to='orders.order', verbose_name='order')),
            ],
            options={
                'verbose_name': 'order status history',
                'verbose_name_plural': 'order status history',
                'ordering': ['created_at', 'id'],
            },
        ),
        migrations.CreateModel(
            name='Shipment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('courier_name', models.CharField(max_length=100, verbose_name='courier')),
                ('tracking_number', models.CharField(blank=True, db_index=True, max_length=64, validators=[django.core.validators.RegexValidator(code='invalid_tracking_number', message='Enter a tracking number of 6 to 40 alphanumeric characters.', regex='^[A-Za-z0-9][A-Za-z0-9\\-]{5,39}$')], verbose_name='tracking number')),
                ('tracking_url', models.URLField(blank=True, max_length=500, verbose_name='tracking URL')),
                ('dispatched_at', models.DateTimeField(blank=True, null=True, verbose_name='dispatched at')),
                ('expected_delivery_date', models.DateField(blank=True, null=True, verbose_name='expected delivery')),
                ('delivered_at', models.DateTimeField(blank=True, null=True, verbose_name='delivered at')),
                ('remarks', models.CharField(blank=True, max_length=255, verbose_name='remarks')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='shipments', to='orders.order', verbose_name='order')),
            ],
            options={
                'verbose_name': 'shipment',
                'verbose_name_plural': 'shipments',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['user', '-created_at'], name='order_user_recent_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status', '-created_at'], name='order_status_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['payment_status', '-created_at'], name='order_payment_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['delivery_status', '-created_at'], name='order_delivery_idx'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(condition=models.Q(('grand_total__gte', Decimal('0'))), name='order_grand_total_not_negative'),
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(condition=models.Q(('subtotal__gte', Decimal('0'))), name='order_subtotal_not_negative'),
        ),
        migrations.AddIndex(
            model_name='orderitem',
            index=models.Index(fields=['order'], name='orderitem_order_idx'),
        ),
        migrations.AddIndex(
            model_name='orderitem',
            index=models.Index(fields=['sku'], name='orderitem_sku_idx'),
        ),
        migrations.AddConstraint(
            model_name='orderitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gte', 1)), name='orderitem_quantity_positive'),
        ),
        migrations.AddIndex(
            model_name='orderstatushistory',
            index=models.Index(fields=['order', 'created_at'], name='statushistory_order_idx'),
        ),
        migrations.AddIndex(
            model_name='shipment',
            index=models.Index(fields=['order', '-created_at'], name='shipment_order_idx'),
        ),
    ]
