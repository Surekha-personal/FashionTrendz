"""Initial schema for the recommendations module.

RecentlyViewed (the browsing trail, owned by a user *or* a session) and
ProductAffinity (the materialised co-purchase graph behind "frequently bought
together").
"""

import django.db.models.deletion
import uuid
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
            name='ProductAffinity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('co_purchase_count', models.PositiveIntegerField(db_index=True, default=0, verbose_name='orders containing both')),
                ('score', models.FloatField(db_index=True, default=0.0, help_text="Share of this product's orders that also contained the other one.", verbose_name='confidence')),
                ('computed_at', models.DateTimeField(auto_now=True, verbose_name='computed at')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='affinities', to='products.product', verbose_name='product')),
                ('related_product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reverse_affinities', to='products.product', verbose_name='bought together with')),
            ],
            options={
                'verbose_name': 'product affinity',
                'verbose_name_plural': 'product affinities',
                'ordering': ['-score', '-co_purchase_count'],
                'indexes': [models.Index(fields=['product', '-score'], name='affinity_lookup_idx')],
                'constraints': [models.UniqueConstraint(fields=('product', 'related_product'), name='unique_product_affinity'), models.CheckConstraint(condition=models.Q(('product', models.F('related_product')), _negated=True), name='affinity_not_self_referential')],
            },
        ),
        migrations.CreateModel(
            name='RecentlyViewed',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('session_key', models.CharField(blank=True, db_index=True, help_text="Identifies a guest's trail before they sign in.", max_length=64, verbose_name='session key')),
                ('viewed_at', models.DateTimeField(auto_now=True, db_index=True, verbose_name='viewed at')),
                ('view_count', models.PositiveIntegerField(default=1, help_text='How often this shopper returned to the product.', verbose_name='times viewed')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recent_views', to='products.product', verbose_name='product')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='recently_viewed', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
            ],
            options={
                'verbose_name': 'recently viewed product',
                'verbose_name_plural': 'recently viewed products',
                'ordering': ['-viewed_at'],
                'indexes': [models.Index(fields=['user', '-viewed_at'], name='recentview_user_idx'), models.Index(fields=['session_key', '-viewed_at'], name='recentview_session_idx'), models.Index(fields=['viewed_at'], name='recentview_cleanup_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(models.Q(('session_key', ''), ('user__isnull', False)), models.Q(('session_key__gt', ''), ('user__isnull', True)), _connector='OR'), name='recentlyviewed_owned_by_user_xor_session'), models.UniqueConstraint(condition=models.Q(('user__isnull', False)), fields=('user', 'product'), name='unique_recent_view_per_user'), models.UniqueConstraint(condition=models.Q(('user__isnull', True)), fields=('session_key', 'product'), name='unique_recent_view_per_session')],
            },
        ),
    ]
