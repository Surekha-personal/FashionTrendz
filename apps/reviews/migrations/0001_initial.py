"""Initial schema for the reviews module.

Review, ReviewImage and HelpfulVote. The unique constraint on ``order_item``
is the one that matters: it is what makes "one review per purchase" survive a
double-tapped submit button.
"""

import apps.catalog.utils
import apps.core.validators
import apps.reviews.validators
import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('orders', '0001_initial'),
        ('products', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('rating', models.PositiveSmallIntegerField(choices=[(1, '1 star'), (2, '2 stars'), (3, '3 stars'), (4, '4 stars'), (5, '5 stars')], db_index=True, verbose_name='rating')),
                ('title', models.CharField(blank=True, max_length=120, validators=[apps.core.validators.validate_no_html], verbose_name='title')),
                ('body', models.TextField(blank=True, max_length=5000, validators=[apps.reviews.validators.validate_review_body, apps.reviews.validators.validate_no_contact_details, apps.core.validators.validate_no_html], verbose_name='review')),
                ('is_verified_purchase', models.BooleanField(db_index=True, default=False, help_text='True when the review is backed by a delivered order line.', verbose_name='verified purchase')),
                ('status', models.CharField(choices=[('pending', 'Pending review'), ('approved', 'Approved'), ('rejected', 'Rejected')], db_index=True, default='pending', max_length=12, verbose_name='moderation status')),
                ('moderated_at', models.DateTimeField(blank=True, null=True, verbose_name='moderated at')),
                ('rejection_reason', models.CharField(blank=True, max_length=255, verbose_name='rejection reason')),
                ('helpful_count', models.PositiveIntegerField(db_index=True, default=0, editable=False, help_text='Denormalised vote count, maintained by the service layer.', verbose_name='helpful votes')),
                ('moderated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='moderated_reviews', to=settings.AUTH_USER_MODEL, verbose_name='moderated by')),
                ('order_item', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='review', to='orders.orderitem', verbose_name='purchased line')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='products.product', verbose_name='product')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
            ],
            options={
                'verbose_name': 'review',
                'verbose_name_plural': 'reviews',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='HelpfulVote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='helpful_votes', to=settings.AUTH_USER_MODEL, verbose_name='customer')),
                ('review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='helpful_votes', to='reviews.review', verbose_name='review')),
            ],
            options={
                'verbose_name': 'helpful vote',
                'verbose_name_plural': 'helpful votes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ReviewImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('image', models.ImageField(upload_to=apps.catalog.utils.UploadPath('reviews/images'), validators=[apps.core.validators.ImageValidator(max_bytes=3145728, min_height=200, min_width=200)], verbose_name='image')),
                ('thumbnail', models.ImageField(blank=True, help_text='Generated on upload from the full image.', null=True, upload_to=apps.catalog.utils.UploadPath('reviews/thumbnails'), verbose_name='thumbnail')),
                ('caption', models.CharField(blank=True, max_length=150, validators=[apps.core.validators.validate_no_html], verbose_name='caption')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, verbose_name='display order')),
                ('review', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='reviews.review', verbose_name='review')),
            ],
            options={
                'verbose_name': 'review image',
                'verbose_name_plural': 'review images',
                'ordering': ['display_order', 'id'],
            },
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['product', 'status', '-created_at'], name='review_product_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['product', 'status', '-helpful_count'], name='review_helpful_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['user', '-created_at'], name='review_user_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['status', '-created_at'], name='review_queue_idx'),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.UniqueConstraint(condition=models.Q(('order_item__isnull', False)), fields=('order_item',), name='unique_review_per_order_item'),
        ),
        migrations.AddConstraint(
            model_name='review',
            constraint=models.CheckConstraint(condition=models.Q(('rating__gte', 1), ('rating__lte', 5)), name='review_rating_within_range'),
        ),
        migrations.AddIndex(
            model_name='helpfulvote',
            index=models.Index(fields=['review', 'user'], name='helpfulvote_lookup_idx'),
        ),
        migrations.AddConstraint(
            model_name='helpfulvote',
            constraint=models.UniqueConstraint(fields=('review', 'user'), name='unique_helpful_vote_per_user'),
        ),
        migrations.AddIndex(
            model_name='reviewimage',
            index=models.Index(fields=['review', 'display_order'], name='reviewimage_order_idx'),
        ),
    ]
