"""Initial schema for the catalog module: Category, SubCategory, Brand, Collection."""

import apps.catalog.utils
import apps.catalog.validators
import apps.core.validators
import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('name', models.CharField(max_length=120, unique=True, validators=[apps.core.validators.validate_no_html], verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('icon', models.ImageField(blank=True, help_text='Small square glyph shown in the mega menu.', null=True, upload_to=apps.catalog.utils.UploadPath('catalog/categories/icons'), validators=[apps.core.validators.ImageValidator(max_bytes=1048576, min_height=64, min_width=64)], verbose_name='icon')),
                ('image', models.ImageField(blank=True, help_text='Card artwork for category grids.', null=True, upload_to=apps.catalog.utils.UploadPath('catalog/categories/images'), validators=[apps.core.validators.ImageValidator(max_bytes=2097152, min_height=200, min_width=200)], verbose_name='tile image')),
                ('banner_image', models.ImageField(blank=True, help_text='Full-width hero on the category landing page.', null=True, upload_to=apps.catalog.utils.UploadPath('catalog/categories/banners'), validators=[apps.core.validators.ImageValidator(max_bytes=4194304, min_height=300, min_width=1200)], verbose_name='banner image')),
                ('menu_image', models.ImageField(blank=True, help_text='Promotional panel inside the mega menu flyout.', null=True, upload_to=apps.catalog.utils.UploadPath('catalog/categories/menu'), validators=[apps.core.validators.ImageValidator(max_bytes=2097152, min_height=200, min_width=200)], verbose_name='menu image')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('is_featured', models.BooleanField(db_index=True, default=False, verbose_name='featured')),
                ('is_trending', models.BooleanField(db_index=True, default=False, verbose_name='trending')),
                ('is_luxury', models.BooleanField(db_index=True, default=False, verbose_name='luxury')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, help_text='Lower numbers appear first.', validators=[apps.catalog.validators.validate_display_order], verbose_name='display order')),
            ],
            options={
                'verbose_name': 'category',
                'verbose_name_plural': 'categories',
                'ordering': ['display_order', 'name'],
                'indexes': [models.Index(fields=['is_active', 'display_order'], name='category_active_order_idx'), models.Index(fields=['is_featured', 'is_active'], name='category_featured_idx')],
            },
        ),
        migrations.CreateModel(
            name='Brand',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('name', models.CharField(max_length=120, unique=True, validators=[apps.core.validators.validate_no_html], verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('logo', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/brands/logos'), validators=[apps.core.validators.ImageValidator(max_bytes=2097152, min_height=200, min_width=200)], verbose_name='logo')),
                ('banner', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/brands/banners'), validators=[apps.core.validators.ImageValidator(max_bytes=4194304, min_height=300, min_width=1200)], verbose_name='banner')),
                ('website', models.URLField(blank=True, max_length=255, verbose_name='website')),
                ('country', models.CharField(blank=True, max_length=100, validators=[apps.core.validators.validate_no_html], verbose_name='country of origin')),
                ('founded_year', models.PositiveSmallIntegerField(blank=True, null=True, validators=[apps.catalog.validators.validate_founded_year], verbose_name='founded year')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('is_featured', models.BooleanField(db_index=True, default=False, verbose_name='featured')),
                ('is_luxury', models.BooleanField(db_index=True, default=False, verbose_name='luxury')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, validators=[apps.catalog.validators.validate_display_order], verbose_name='display order')),
                ('popularity_score', models.PositiveIntegerField(db_index=True, default=0, help_text="Ranking weight for the 'popular brands' rail. Maintained editorially until order data exists to derive it from.", verbose_name='popularity score')),
                ('categories', models.ManyToManyField(blank=True, related_name='brands', to='catalog.category', verbose_name='categories')),
            ],
            options={
                'verbose_name': 'brand',
                'verbose_name_plural': 'brands',
                'ordering': ['display_order', 'name'],
                'indexes': [models.Index(fields=['is_active', 'display_order'], name='brand_active_order_idx'), models.Index(fields=['is_active', '-popularity_score'], name='brand_popularity_idx'), models.Index(fields=['is_luxury', 'is_active'], name='brand_luxury_idx')],
            },
        ),
        migrations.CreateModel(
            name='Collection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('title', models.CharField(max_length=150, unique=True, validators=[apps.core.validators.validate_no_html], verbose_name='title')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('type', models.CharField(choices=[('new_arrivals', 'New Arrivals'), ('trending', 'Trending'), ('luxury', 'Luxury'), ('editors_picks', "Editor's Picks"), ('best_sellers', 'Best Sellers'), ('festival', 'Festival Collection'), ('wedding', 'Wedding Collection'), ('summer', 'Summer Collection'), ('winter', 'Winter Collection')], db_index=True, default='new_arrivals', max_length=24, verbose_name='type')),
                ('image', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/collections/images'), validators=[apps.core.validators.ImageValidator(max_bytes=2097152, min_height=200, min_width=200)], verbose_name='tile image')),
                ('banner', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/collections/banners'), validators=[apps.core.validators.ImageValidator(max_bytes=4194304, min_height=300, min_width=1200)], verbose_name='banner')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('is_featured', models.BooleanField(db_index=True, default=False, help_text='Show this collection on the homepage and in the mega menu.', verbose_name='featured')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, validators=[apps.catalog.validators.validate_display_order], verbose_name='display order')),
                ('categories', models.ManyToManyField(blank=True, related_name='collections', to='catalog.category', verbose_name='categories')),
            ],
            options={
                'verbose_name': 'collection',
                'verbose_name_plural': 'collections',
                'ordering': ['display_order', 'title'],
                'indexes': [models.Index(fields=['is_active', 'display_order'], name='collection_active_order_idx'), models.Index(fields=['type', 'is_active'], name='collection_type_idx')],
            },
        ),
        migrations.CreateModel(
            name='SubCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('name', models.CharField(max_length=120, validators=[apps.core.validators.validate_no_html], verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('image', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/subcategories/images'), validators=[apps.core.validators.ImageValidator(max_bytes=2097152, min_height=200, min_width=200)], verbose_name='tile image')),
                ('banner_image', models.ImageField(blank=True, null=True, upload_to=apps.catalog.utils.UploadPath('catalog/subcategories/banners'), validators=[apps.core.validators.ImageValidator(max_bytes=4194304, min_height=300, min_width=1200)], verbose_name='banner image')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, validators=[apps.catalog.validators.validate_display_order], verbose_name='display order')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='subcategories', to='catalog.category', verbose_name='category')),
            ],
            options={
                'verbose_name': 'subcategory',
                'verbose_name_plural': 'subcategories',
                'ordering': ['category__display_order', 'display_order', 'name'],
                'indexes': [models.Index(fields=['category', 'is_active', 'display_order'], name='subcat_cat_active_order_idx')],
                'constraints': [models.UniqueConstraint(fields=('category', 'name'), name='unique_subcategory_name_per_category')],
            },
        ),
    ]
