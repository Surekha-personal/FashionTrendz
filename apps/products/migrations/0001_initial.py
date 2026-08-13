"""Initial schema for the products module.

Product, ProductTag, ProductImage, ProductVariant, ProductAttribute
and ProductSpecification.
"""

import apps.catalog.utils
import apps.core.validators
import apps.products.validators
import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductTag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('name', models.CharField(max_length=80, unique=True, validators=[apps.core.validators.validate_no_html], verbose_name='name')),
                ('description', models.TextField(blank=True, verbose_name='description')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
            ],
            options={
                'verbose_name': 'product tag',
                'verbose_name_plural': 'product tags',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('slug', models.SlugField(max_length=255, unique=True, verbose_name='slug')),
                ('meta_title', models.CharField(blank=True, max_length=70, verbose_name='meta title')),
                ('meta_description', models.CharField(blank=True, max_length=170, verbose_name='meta description')),
                ('meta_keywords', models.CharField(blank=True, max_length=255, verbose_name='meta keywords')),
                ('name', models.CharField(db_index=True, max_length=200, validators=[apps.core.validators.validate_no_html], verbose_name='name')),
                ('short_description', models.CharField(blank=True, help_text='One-line summary shown on cards and in quick view.', max_length=300, verbose_name='short description')),
                ('long_description', models.TextField(blank=True, verbose_name='long description')),
                ('sku', models.CharField(max_length=50, unique=True, validators=[django.core.validators.RegexValidator(code='invalid_sku', message='Enter a SKU of 3-50 characters using uppercase letters, digits and hyphens.', regex='^[A-Z0-9][A-Z0-9-]{2,49}$')], verbose_name='SKU')),
                ('barcode', models.CharField(blank=True, max_length=14, validators=[django.core.validators.RegexValidator(code='invalid_barcode', message='Enter a barcode of 8 to 14 digits.', regex='^\\d{8,14}$')], verbose_name='barcode')),
                ('mrp', models.DecimalField(decimal_places=2, help_text='Maximum retail price, before discount.', max_digits=12, validators=[apps.core.validators.validate_price], verbose_name='MRP')),
                ('selling_price', models.DecimalField(db_index=True, decimal_places=2, max_digits=12, validators=[apps.core.validators.validate_price], verbose_name='selling price')),
                ('discount_percentage', models.DecimalField(db_index=True, decimal_places=2, default=Decimal('0.00'), editable=False, help_text='Derived from MRP and selling price on save.', max_digits=5, verbose_name='discount percentage')),
                ('discount_amount', models.DecimalField(decimal_places=2, default=Decimal('0.00'), editable=False, max_digits=12, verbose_name='discount amount')),
                ('tax_percentage', models.DecimalField(decimal_places=2, default=Decimal('5.00'), max_digits=5, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('100'))], verbose_name='tax percentage')),
                ('currency', models.CharField(choices=[('INR', 'Indian Rupee'), ('USD', 'US Dollar'), ('EUR', 'Euro'), ('GBP', 'Pound Sterling'), ('AED', 'UAE Dirham')], default='INR', max_length=3, verbose_name='currency')),
                ('gender', models.CharField(choices=[('male', 'Male'), ('female', 'Female'), ('unisex', 'Unisex'), ('other', 'Other'), ('undisclosed', 'Prefer not to say')], db_index=True, default='unisex', max_length=12, verbose_name='gender')),
                ('material', models.CharField(blank=True, choices=[('cotton', 'Cotton'), ('linen', 'Linen'), ('silk', 'Silk'), ('wool', 'Wool'), ('denim', 'Denim'), ('leather', 'Leather'), ('polyester', 'Polyester'), ('rayon', 'Rayon'), ('viscose', 'Viscose'), ('georgette', 'Georgette'), ('chiffon', 'Chiffon'), ('velvet', 'Velvet'), ('satin', 'Satin'), ('khadi', 'Khadi'), ('blended', 'Blended'), ('other', 'Other')], db_index=True, max_length=16, verbose_name='material')),
                ('fit', models.CharField(blank=True, choices=[('slim', 'Slim fit'), ('regular', 'Regular fit'), ('relaxed', 'Relaxed fit'), ('oversized', 'Oversized'), ('bodycon', 'Bodycon'), ('a_line', 'A-line'), ('straight', 'Straight'), ('tapered', 'Tapered')], max_length=12, verbose_name='fit')),
                ('sleeve_type', models.CharField(blank=True, choices=[('sleeveless', 'Sleeveless'), ('cap', 'Cap sleeve'), ('short', 'Short sleeve'), ('three_quarter', 'Three-quarter sleeve'), ('long', 'Long sleeve'), ('puff', 'Puff sleeve'), ('bell', 'Bell sleeve'), ('na', 'Not applicable')], max_length=16, verbose_name='sleeve type')),
                ('neck_type', models.CharField(blank=True, choices=[('round', 'Round neck'), ('v_neck', 'V-neck'), ('collared', 'Collared'), ('boat', 'Boat neck'), ('square', 'Square neck'), ('halter', 'Halter neck'), ('mandarin', 'Mandarin collar'), ('sweetheart', 'Sweetheart'), ('na', 'Not applicable')], max_length=16, verbose_name='neck type')),
                ('pattern', models.CharField(blank=True, choices=[('solid', 'Solid'), ('printed', 'Printed'), ('floral', 'Floral'), ('striped', 'Striped'), ('checked', 'Checked'), ('embroidered', 'Embroidered'), ('colourblock', 'Colourblock'), ('animal', 'Animal print'), ('abstract', 'Abstract'), ('woven', 'Woven design')], max_length=16, verbose_name='pattern')),
                ('occasion', models.CharField(blank=True, choices=[('casual', 'Casual'), ('formal', 'Formal'), ('party', 'Party'), ('wedding', 'Wedding'), ('festive', 'Festive'), ('sports', 'Sports'), ('lounge', 'Lounge'), ('beach', 'Beach'), ('work', 'Work')], db_index=True, max_length=12, verbose_name='occasion')),
                ('season', models.CharField(choices=[('summer', 'Summer'), ('winter', 'Winter'), ('monsoon', 'Monsoon'), ('spring', 'Spring'), ('autumn', 'Autumn'), ('all_season', 'All season')], db_index=True, default='all_season', max_length=12, verbose_name='season')),
                ('country_of_origin', models.CharField(blank=True, max_length=100, validators=[apps.core.validators.validate_no_html], verbose_name='country of origin')),
                ('weight_grams', models.PositiveIntegerField(blank=True, help_text='Shipping weight, used for courier rate calculation.', null=True, verbose_name='weight (grams)')),
                ('dimensions', models.CharField(blank=True, help_text="Packed size as 'L x W x H' in centimetres.", max_length=60, validators=[django.core.validators.RegexValidator(code='invalid_dimensions', message="Enter dimensions as 'L x W x H' in centimetres, e.g. 30 x 20 x 5.", regex='^\\d+(\\.\\d+)?\\s*x\\s*\\d+(\\.\\d+)?\\s*x\\s*\\d+(\\.\\d+)?$')], verbose_name='dimensions')),
                ('warranty', models.CharField(blank=True, max_length=150, verbose_name='warranty')),
                ('care_instructions', models.TextField(blank=True, verbose_name='care instructions')),
                ('return_policy', models.CharField(blank=True, max_length=200, verbose_name='return policy')),
                ('shipping_info', models.CharField(blank=True, max_length=200, verbose_name='shipping info')),
                ('estimated_delivery_days', models.PositiveSmallIntegerField(default=5, verbose_name='estimated delivery (days)')),
                ('rating_average', models.DecimalField(db_index=True, decimal_places=2, default=Decimal('0.00'), max_digits=3, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('5'))], verbose_name='rating average')),
                ('rating_count', models.PositiveIntegerField(default=0, verbose_name='rating count')),
                ('review_count', models.PositiveIntegerField(default=0, verbose_name='review count')),
                ('wishlist_count', models.PositiveIntegerField(default=0, verbose_name='wishlist count')),
                ('view_count', models.PositiveIntegerField(db_index=True, default=0, verbose_name='view count')),
                ('purchase_count', models.PositiveIntegerField(db_index=True, default=0, verbose_name='purchase count')),
                ('total_stock', models.IntegerField(db_index=True, default=0, editable=False, help_text='Sum of active variant stock minus reservations.', verbose_name='total available stock')),
                ('stock_status', models.CharField(choices=[('in_stock', 'In stock'), ('low_stock', 'Low stock'), ('out_of_stock', 'Out of stock'), ('discontinued', 'Discontinued')], db_index=True, default='out_of_stock', editable=False, max_length=16, verbose_name='stock status')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('is_featured', models.BooleanField(db_index=True, default=False, verbose_name='featured')),
                ('is_new_arrival', models.BooleanField(db_index=True, default=False, verbose_name='new arrival')),
                ('is_best_seller', models.BooleanField(db_index=True, default=False, verbose_name='best seller')),
                ('is_trending', models.BooleanField(db_index=True, default=False, verbose_name='trending')),
                ('is_luxury', models.BooleanField(db_index=True, default=False, verbose_name='luxury')),
                ('is_recommended', models.BooleanField(db_index=True, default=False, verbose_name='recommended')),
                ('is_returnable', models.BooleanField(default=True, verbose_name='returnable')),
                ('published_at', models.DateTimeField(blank=True, db_index=True, help_text='Products are hidden until this time passes. Blank means unpublished.', null=True, verbose_name='published at')),
                ('brand', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='catalog.brand', verbose_name='brand')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='catalog.category', verbose_name='category')),
                ('collection', models.ForeignKey(blank=True, help_text='Optional editorial collection this product belongs to.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products', to='catalog.collection', verbose_name='collection')),
                ('subcategory', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='products', to='catalog.subcategory', verbose_name='subcategory')),
                ('tags', models.ManyToManyField(blank=True, related_name='products', to='products.producttag', verbose_name='tags')),
            ],
            options={
                'verbose_name': 'product',
                'verbose_name_plural': 'products',
                'ordering': ['-published_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ProductVariant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('sku', models.CharField(max_length=50, unique=True, validators=[django.core.validators.RegexValidator(code='invalid_sku', message='Enter a SKU of 3-50 characters using uppercase letters, digits and hyphens.', regex='^[A-Z0-9][A-Z0-9-]{2,49}$')], verbose_name='SKU')),
                ('barcode', models.CharField(blank=True, max_length=14, validators=[django.core.validators.RegexValidator(code='invalid_barcode', message='Enter a barcode of 8 to 14 digits.', regex='^\\d{8,14}$')], verbose_name='barcode')),
                ('color', models.CharField(db_index=True, max_length=40, verbose_name='colour')),
                ('color_code', models.CharField(blank=True, help_text='Hex swatch shown on the product page, e.g. #1E3A8A.', max_length=7, verbose_name='colour code')),
                ('size', models.CharField(choices=[('XS', 'XS'), ('S', 'S'), ('M', 'M'), ('L', 'L'), ('XL', 'XL'), ('XXL', 'XXL'), ('3XL', '3XL'), ('FREE', 'Free size'), ('UK6', 'UK 6'), ('UK7', 'UK 7'), ('UK8', 'UK 8'), ('UK9', 'UK 9'), ('UK10', 'UK 10'), ('UK11', 'UK 11')], db_index=True, max_length=8, verbose_name='size')),
                ('stock', models.PositiveIntegerField(default=0, validators=[apps.products.validators.validate_stock], verbose_name='stock on hand')),
                ('reserved_stock', models.PositiveIntegerField(default=0, help_text='Units held by in-flight checkouts and unshipped orders.', verbose_name='reserved stock')),
                ('price_override', models.DecimalField(blank=True, decimal_places=2, help_text='Set only when this variant costs more than the base product.', max_digits=12, null=True, validators=[apps.core.validators.validate_price], verbose_name='price override')),
                ('image_override', models.ImageField(blank=True, help_text='Swatch-specific photograph, shown when this colour is selected.', null=True, upload_to=apps.catalog.utils.UploadPath('products/variants'), validators=[apps.core.validators.ImageValidator(max_bytes=5242880, min_height=600, min_width=400)], verbose_name='variant image')),
                ('weight_grams', models.PositiveIntegerField(blank=True, null=True, verbose_name='weight (grams)')),
                ('is_active', models.BooleanField(db_index=True, default=True, verbose_name='active')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='variants', to='products.product', verbose_name='product')),
            ],
            options={
                'verbose_name': 'product variant',
                'verbose_name_plural': 'product variants',
                'ordering': ['product', 'color', 'size'],
            },
        ),
        migrations.CreateModel(
            name='ProductAttribute',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('key', models.CharField(max_length=80, validators=[apps.core.validators.validate_no_html], verbose_name='key')),
                ('value', models.CharField(max_length=255, validators=[apps.core.validators.validate_no_html], verbose_name='value')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attributes', to='products.product', verbose_name='product')),
            ],
            options={
                'verbose_name': 'product attribute',
                'verbose_name_plural': 'product attributes',
                'ordering': ['key'],
                'constraints': [models.UniqueConstraint(fields=('product', 'key'), name='unique_attribute_key_per_product')],
            },
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('image', models.ImageField(upload_to=apps.catalog.utils.UploadPath('products/images'), validators=[apps.core.validators.ImageValidator(max_bytes=5242880, min_height=600, min_width=400)], verbose_name='image')),
                ('thumbnail', models.ImageField(blank=True, help_text='Generated on save from the full image if left blank.', null=True, upload_to=apps.catalog.utils.UploadPath('products/thumbnails'), validators=[apps.core.validators.ImageValidator(max_bytes=1048576, min_height=100, min_width=100)], verbose_name='thumbnail')),
                ('alt_text', models.CharField(blank=True, help_text='Screen-reader description. Falls back to the product name.', max_length=200, verbose_name='alt text')),
                ('display_order', models.PositiveSmallIntegerField(db_index=True, default=0, verbose_name='display order')),
                ('is_primary', models.BooleanField(db_index=True, default=False, verbose_name='primary')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='images', to='products.product', verbose_name='product')),
            ],
            options={
                'verbose_name': 'product image',
                'verbose_name_plural': 'product images',
                'ordering': ['-is_primary', 'display_order', 'id'],
                'indexes': [models.Index(fields=['product', 'display_order'], name='image_product_order_idx')],
                'constraints': [models.UniqueConstraint(condition=models.Q(('is_primary', True)), fields=('product',), name='unique_primary_image_per_product')],
            },
        ),
        migrations.CreateModel(
            name='ProductSpecification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='created at')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated at')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True, verbose_name='public id')),
                ('label', models.CharField(max_length=80, validators=[apps.core.validators.validate_no_html], verbose_name='label')),
                ('value', models.CharField(max_length=255, validators=[apps.core.validators.validate_no_html], verbose_name='value')),
                ('display_order', models.PositiveSmallIntegerField(default=0, verbose_name='display order')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='specifications', to='products.product', verbose_name='product')),
            ],
            options={
                'verbose_name': 'product specification',
                'verbose_name_plural': 'product specifications',
                'ordering': ['display_order', 'label'],
                'constraints': [models.UniqueConstraint(fields=('product', 'label'), name='unique_specification_label_per_product')],
            },
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-published_at'], name='product_visible_new_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['category', 'is_active', '-published_at'], name='product_cat_listing_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['subcategory', 'is_active', '-published_at'], name='product_subcat_listing_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['brand', 'is_active', '-published_at'], name='product_brand_listing_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', 'selling_price'], name='product_price_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-discount_percentage'], name='product_discount_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-rating_average'], name='product_rating_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_active', '-purchase_count'], name='product_bestseller_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_featured', 'is_active'], name='product_featured_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_trending', 'is_active'], name='product_trending_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_new_arrival', 'is_active'], name='product_newarrival_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['is_luxury', 'is_active'], name='product_luxury_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['gender', 'is_active'], name='product_gender_idx'),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.CheckConstraint(condition=models.Q(('selling_price__lte', models.F('mrp'))), name='product_selling_price_not_above_mrp'),
        ),
        migrations.AddConstraint(
            model_name='product',
            constraint=models.CheckConstraint(condition=models.Q(('mrp__gte', Decimal('0'))), name='product_mrp_not_negative'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['product', 'is_active'], name='variant_product_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['color'], name='variant_color_idx'),
        ),
        migrations.AddIndex(
            model_name='productvariant',
            index=models.Index(fields=['size'], name='variant_size_idx'),
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.UniqueConstraint(fields=('product', 'color', 'size'), name='unique_variant_per_product'),
        ),
        migrations.AddConstraint(
            model_name='productvariant',
            constraint=models.CheckConstraint(condition=models.Q(('reserved_stock__lte', models.F('stock'))), name='variant_reserved_not_above_stock'),
        ),
    ]
