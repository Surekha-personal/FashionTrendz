# Field map — requested spec → shipped backend

Every field in the schema brief already exists. Most carry a different, more
precise name. Nothing was renamed, so this table is the translation layer for
anyone working from the brief.

**Only one model was genuinely missing: `Banner`.**

---

## User → `users.User` (`users_user`)

| Requested | Actual | Note |
|---|---|---|
| `id` | `id` | BIGSERIAL |
| `first_name` `last_name` | same | |
| `email` | `email` | UNIQUE; this is the login identifier — there is no username |
| `phone` | **`mobile_number`** | VARCHAR(16), validated |
| `profile_image` | `profile_image` | |
| `gender` | `gender` | male \| female \| other \| undisclosed |
| `date_of_birth` | `date_of_birth` | |
| `is_verified` | **`is_email_verified`** + **`is_mobile_verified`** | Two flags, because verifying an address does not verify a number |
| `is_active` `is_staff` | same | |
| `created_at` `updated_at` | same | |

## Brand → `catalog.Brand` (`catalog_brand`)

All six requested fields present (`name`, `slug`, `logo`, `description`,
`is_active`). Also carries `banner`, `website`, `country`, `founded_year`,
`is_featured`, `is_luxury`, `display_order`, `popularity_score` and an SEO block.

## Category → `catalog.Category` + `catalog.SubCategory`

| Requested | Actual |
|---|---|
| `name` `slug` `image` `description` `is_active` | same, on `Category` |
| `parent_category` | **`catalog_subcategory.category_id`** |

Two tables rather than a self-referential tree, by your instruction. The
recommendation engine treats subcategory as the "related products"
neighbourhood — `Dresses` is useful, `Women` is the whole store.

## Product → `products.Product` (`products_product`)

| Requested | Actual | Note |
|---|---|---|
| `price` | **`mrp`** | List price |
| `discount_price` | **`selling_price`** | What the customer pays; CHECK `selling_price <= mrp` |
| `discount_percentage` | same | |
| `stock` | **`total_stock`** | Roll-up of variant stock, maintained by `sync_product_stock()` |
| `description` | **`long_description`** | |
| `short_description` | same | |
| `rating` | **`rating_average`** | NUMERIC(3,2), approved reviews only |
| `review_count` | same | |
| `gender` `material` `fit` `occasion` `season` | same | Plus `pattern`, `sleeve_type`, `neck_type` |
| `color` | **`products_productvariant.color`** | Colour belongs to the variant — see below |
| `is_featured` `is_trending` `is_new_arrival` `is_active` | same | Plus `is_best_seller`, `is_luxury`, `is_recommended` |
| `created_at` `updated_at` | same | |

`color` was **not** added to `Product`. A product has many colourways; storing
one on the parent would duplicate variant data and the two can disagree. The
API surfaces the distinct set through the variant list on
`GET /products/{slug}`.

## Variants → `products.ProductVariant`

Requested `ProductSize` + `ProductColor`; kept as `ProductVariant` by your
instruction. One row per **colour + size**, holding `stock` and
`reserved_stock`, `UNIQUE(product, color, size)` and
`CHECK reserved_stock <= stock`.

Splitting them would make "Navy in M" unrepresentable — you would have M stock
and Navy existence, separately — and oversell protection depends on reserving
against the exact sellable unit.

## Images → `products.ProductImage`

Reused, not recreated. `product`, `image`, `alt_text`, `display_order`, plus
`thumbnail` and `is_primary` with a partial unique index enforcing one primary
per product. Seeding now creates **4–6 per product** (see below).

## Wishlist / Cart / Orders / Reviews / Coupons / Notifications

| Requested | Actual |
|---|---|
| `Wishlist(user, product)` | `wishlist_wishlist` (1:1 user) + `wishlist_wishlistitem` |
| `CartItem.size` `.color` | **`cart_cartitem.variant_id`** — kept, per instruction |
| `Order.shipping` | **`shipping_charge`** |
| `Order.total` | **`grand_total`** |
| `Review.review` | **`body`**; `images` → `reviews_reviewimage` |
| `Coupon.discount_value` | **`value`** |
| `Coupon.minimum_order` | **`min_cart_value`** |
| `Coupon.expiry_date` | **`valid_until`** (paired with `valid_from`) |
| `Notification.title` `.message` `.type` | **`subject`** `body` `category` |

---

## New: `banner.Banner` (`banner_banner`)

The one model that did not exist.

| Requested | Shipped |
|---|---|
| `title` `subtitle` `image` `button_text` `button_link` `display_order` `is_active` | all present |
| — | `placement`, `mobile_image`, `alt_text`, `starts_at`, `ends_at`, `impression_count`, `click_count` |

`placement` (`hero`, `strip`, `grid_left`, `grid_right`, `category_top`,
`footer`) is what lets a merchandiser add a slot without a frontend change.
`starts_at` / `ends_at` mean a midnight campaign does not need someone awake at
midnight.

### Endpoints

```
GET  /api/v1/banners/?placement=hero    Live banners, optionally one slot
GET  /api/v1/banners/homepage/          All live banners grouped by placement
POST /api/v1/banners/{uuid}/impression/ Count a view   (F() expression)
POST /api/v1/banners/{uuid}/click/      Count a click

GET|POST        /api/v1/admin/banners/           Staff CRUD
GET|PATCH|DELETE /api/v1/admin/banners/{uuid}/
GET             /api/v1/admin/banners/placements/
```

---

## Seed commands

```bash
python manage.py seed_categories          # 20 categories, 137 subcategories
python manage.py seed_brands              # 15 brands
python manage.py seed_products --count 150
python manage.py seed_banners             # 8 banners across 6 placements
```

All idempotent — re-running updates rather than duplicating, which matters
because products reference brands and categories with `ON DELETE PROTECT`.

`seed_catalog` (10 categories, 50 brands) is untouched and still works; its
tests pin those counts. `seed_categories` imports its category list and adds ten
more, so the taxonomy has one definition.

`seed_products` now generates **4–6 `ProductImage` rows per product** — it
previously created none. Images are generated locally with Pillow, not
downloaded: a seed command that reaches the network fails on an air-gapped CI
box and makes the fixture depend on someone else's uptime. Colours are hashed
from the SKU, so a product keeps its appearance across re-runs.

`--no-images` skips generation (roughly 10× faster); `--images-per-product N`
fixes the gallery size.

---

## Image URLs

Every image field returns an **absolute URL**. DRF's `ImageField` does this when
the serializer has a `request` in context, which every view supplies. A relative
`/media/...` path would force the client to know the API origin and would break
when media moves to S3.

`MEDIA_ROOT` and `MEDIA_URL` were already configured; `STORAGES["default"]`
switches to S3 automatically when `AWS_STORAGE_BUCKET_NAME` is set.
