"""Initial schema for the coupons module: Coupon and CouponUsage."""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0001_initial'),
        ('orders', '0001_initial'),
        ('products', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Coupon',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('code', models.CharField(db_index=True, help_text='Uppercase. What the customer types at checkout.', max_length=40, unique=True, validators=[django.core.validators.RegexValidator(code='invalid_coupon_code', message='Enter a code of 3-40 characters using uppercase letters, digits and hyphens.', regex='^[A-Z0-9][A-Z0-9-]{2,39}$')], verbose_name='code')),
                ('description', models.CharField(blank=True, max_length=255, verbose_name='description')),
                ('discount_type', models.CharField(choices=[('flat', 'Flat amount off'), ('percentage', 'Percentage off'), ('free_shipping', 'Free shipping')], default='percentage', max_length=16, verbose_name='type')),
                ('value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Percentage (0-100) or flat amount, depending on the type.', max_digits=12, verbose_name='value')),
                ('max_discount', models.DecimalField(blank=True, decimal_places=2, help_text="Caps a percentage coupon. Without it, '50% off' on a ₹90,000 coat is a ₹45,000 giveaway.", max_digits=12, null=True, verbose_name='maximum discount')),
                ('min_cart_value', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='minimum cart value')),
                ('currency', models.CharField(default='INR', max_length=3, verbose_name='currency')),
                ('max_uses', models.PositiveIntegerField(default=0, help_text='Total redemptions allowed across all customers. 0 means unlimited.', verbose_name='maximum uses')),
                ('uses_per_user', models.PositiveSmallIntegerField(default=1, help_text='0 means unlimited.', verbose_name='uses per customer')),
                ('times_used', models.PositiveIntegerField(default=0, editable=False, help_text='Denormalised redemption count, maintained by the service layer.', verbose_name='times used')),
                ('valid_from', models.DateTimeField(default=django.utils.timezone.now, verbose_name='valid from')),
                ('valid_until', models.DateTimeField(blank=True, help_text='Blank means the coupon never expires.', null=True, verbose_name='valid until')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('is_public', models.BooleanField(db_index=True, default=True, help_text="Show in the storefront's offers list. Turn off for private codes.", verbose_name='public')),
                ('first_order_only', models.BooleanField(default=False, help_text='Redeemable only by customers who have never ordered.', verbose_name='first order only')),
                ('brands', models.ManyToManyField(blank=True, related_name='coupons', to='catalog.brand', verbose_name='brands')),
                ('categories', models.ManyToManyField(blank=True, related_name='coupons', to='catalog.category', verbose_name='categories')),
                ('products', models.ManyToManyField(blank=True, related_name='coupons', to='products.product', verbose_name='products')),
            ],
            options={
                'verbose_name': 'coupon',
                'verbose_name_plural': 'coupons',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='CouponUsage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('discount_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='discount applied')),
                ('is_released', models.BooleanField(db_index=True, default=False, help_text="Set when the order was cancelled, returning the redemption to the customer's allowance.", verbose_name='released')),
                ('released_at', models.DateTimeField(blank=True, null=True, verbose_name='released at')),
                ('coupon', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usages', to='coupons.coupon', verbose_name='coupon')),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='coupon_usages', to='orders.order', verbose_name='order')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coupon_usages', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
            ],
            options={
                'verbose_name': 'coupon usage',
                'verbose_name_plural': 'coupon usages',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='coupon',
            index=models.Index(fields=['is_active', 'valid_from', 'valid_until'], name='coupon_window_idx'),
        ),
        migrations.AddIndex(
            model_name='coupon',
            index=models.Index(fields=['is_public', 'is_active'], name='coupon_public_idx'),
        ),
        migrations.AddConstraint(
            model_name='coupon',
            constraint=models.CheckConstraint(condition=models.Q(('value__gte', Decimal('0'))), name='coupon_value_not_negative'),
        ),
        migrations.AddConstraint(
            model_name='coupon',
            constraint=models.CheckConstraint(condition=models.Q(('min_cart_value__gte', Decimal('0'))), name='coupon_min_cart_not_negative'),
        ),
        migrations.AddConstraint(
            model_name='coupon',
            constraint=models.CheckConstraint(condition=models.Q(('valid_until__isnull', True), ('valid_until__gt', models.F('valid_from')), _connector='OR'), name='coupon_window_ordered'),
        ),
        migrations.AddIndex(
            model_name='couponusage',
            index=models.Index(fields=['coupon', 'user'], name='couponusage_coupon_user_idx'),
        ),
        migrations.AddIndex(
            model_name='couponusage',
            index=models.Index(fields=['user', '-created_at'], name='couponusage_user_idx'),
        ),
        migrations.AddConstraint(
            model_name='couponusage',
            constraint=models.UniqueConstraint(condition=models.Q(('order__isnull', False)), fields=('coupon', 'order'), name='unique_coupon_usage_per_order'),
        ),
    ]
