"""Initial schema for the cart module: Cart and CartItem."""

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
            name='Cart',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('session_key', models.CharField(blank=True, db_index=True, help_text='Identifies a guest cart before the shopper signs in.', max_length=64, verbose_name='session key')),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Cleared when the cart is converted into an order.', verbose_name='active')),
                ('coupon_code', models.CharField(blank=True, help_text='Captured for the future coupon module; not yet validated.', max_length=40, verbose_name='coupon code')),
                ('coupon_discount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), editable=False, max_digits=12, verbose_name='coupon discount')),
                ('currency', models.CharField(choices=[('INR', 'Indian Rupee'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'Pound Sterling'), ('AED', 'UAE Dirham')], default='INR', max_length=3, verbose_name='currency')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='carts', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'cart',
                'verbose_name_plural': 'carts',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='CartItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('quantity', models.PositiveSmallIntegerField(default=1, verbose_name='quantity')),
                ('saved_for_later', models.BooleanField(db_index=True, default=False, verbose_name='saved for later')),
                ('unit_price', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='unit price')),
                ('unit_mrp', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='unit MRP')),
                ('discount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='line discount')),
                ('tax', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=12, verbose_name='line tax')),
                ('subtotal', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Unit price times quantity, before tax.', max_digits=12, verbose_name='subtotal')),
                ('total', models.DecimalField(decimal_places=2, default=Decimal('0.00'), help_text='Subtotal — tax is quoted separately, not added twice.', max_digits=12, verbose_name='total')),
                ('cart', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='cart.cart', verbose_name='cart')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cart_items', to='products.product', verbose_name='product')),
                ('variant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='cart_items', to='products.productvariant', verbose_name='variant')),
            ],
            options={
                'verbose_name': 'cart item',
                'verbose_name_plural': 'cart items',
                'ordering': ['saved_for_later', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['user', 'is_active'], name='cart_user_active_idx'),
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['session_key', 'is_active'], name='cart_session_active_idx'),
        ),
        migrations.AddIndex(
            model_name='cart',
            index=models.Index(fields=['is_active', '-updated_at'], name='cart_abandoned_idx'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('session_key', ''), ('user__isnull', False)), models.Q(('session_key__gt', ''), ('user__isnull', True)), _connector='OR'), name='cart_owned_by_user_xor_session'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True), ('user__isnull', False)), fields=('user',), name='unique_active_cart_per_user'),
        ),
        migrations.AddConstraint(
            model_name='cart',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True), ('user__isnull', True)), fields=('session_key',), name='unique_active_cart_per_session'),
        ),
        migrations.AddIndex(
            model_name='cartitem',
            index=models.Index(fields=['cart', 'saved_for_later'], name='cartitem_cart_saved_idx'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.UniqueConstraint(fields=('cart', 'variant'), name='unique_variant_per_cart'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__gte', 1)), name='cartitem_quantity_at_least_one'),
        ),
        migrations.AddConstraint(
            model_name='cartitem',
            constraint=models.CheckConstraint(condition=models.Q(('quantity__lte', 10)), name='cartitem_quantity_within_limit'),
        ),
    ]
