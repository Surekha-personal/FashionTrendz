"""Initial schema for the homepage banner module.

One table. Scheduled promotional content by placement, with a CHECK that a
banner's window cannot close before it opens.
"""

import apps.catalog.utils
import apps.core.validators
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Banner',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('title', models.CharField(max_length=150, validators=[apps.core.validators.validate_no_html], verbose_name='title')),
                ('subtitle', models.CharField(blank=True, max_length=255, validators=[apps.core.validators.validate_no_html], verbose_name='subtitle')),
                ('placement', models.CharField(choices=[('hero', 'Homepage hero carousel'), ('strip', 'Homepage promotional strip'), ('grid_left', 'Homepage grid — left tile'), ('grid_right', 'Homepage grid — right tile'), ('category_top', 'Category landing header'), ('footer', 'Footer promotion')], db_index=True, default='hero', max_length=16, verbose_name='placement')),
                ('image', models.ImageField(help_text='Wide crop, shown at tablet width and above.', upload_to=apps.catalog.utils.UploadPath('banners/desktop'), verbose_name='desktop image')),
                ('mobile_image', models.ImageField(blank=True, help_text='Portrait crop for phones. Falls back to the desktop image.', null=True, upload_to=apps.catalog.utils.UploadPath('banners/mobile'), verbose_name='mobile image')),
                ('alt_text', models.CharField(blank=True, help_text='Required for accessibility; describes the image, not the offer.', max_length=200, validators=[apps.core.validators.validate_no_html], verbose_name='alt text')),
                ('button_text', models.CharField(blank=True, max_length=40, validators=[apps.core.validators.validate_no_html], verbose_name='button text')),
                ('button_link', models.CharField(blank=True, max_length=500, verbose_name='button link')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, verbose_name='display order')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('starts_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='starts at')),
                ('ends_at', models.DateTimeField(blank=True, help_text='Leave blank to run indefinitely.', null=True, verbose_name='ends at')),
                ('impression_count', models.PositiveIntegerField(default=0, editable=False, verbose_name='impressions')),
                ('click_count', models.PositiveIntegerField(default=0, editable=False, verbose_name='clicks')),
            ],
            options={
                'verbose_name': 'banner',
                'verbose_name_plural': 'banners',
                'ordering': ['placement', 'display_order', '-created_at'],
                'indexes': [models.Index(fields=['placement', 'is_active', 'display_order'], name='banner_placement_idx'), models.Index(fields=['is_active', 'starts_at', 'ends_at'], name='banner_window_idx')],
                'constraints': [models.CheckConstraint(condition=models.Q(('ends_at__isnull', True), ('ends_at__gt', models.F('starts_at')), _connector='OR'), name='banner_window_ordered')],
            },
        ),
    ]
