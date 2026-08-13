# Seeding the database

Populates every existing table. **No schema changes** — these commands only
write rows through the models that are already there.

```bash
python manage.py seed_everything
```

That runs all eleven seeders in dependency order and takes roughly 2–4 minutes
at full scale on Postgres.

---

## Scales

| Scale | Products | Customers | Orders | Reviews |
|---|---|---|---|---|
| `small` | 60 | 40 | 120 | 200 |
| `medium` | 200 | 100 | 500 | 1,200 |
| `full` *(default)* | 500 | 200 | 1,200 | 3,000 |
| `large` | 1,500 | 600 | 5,000 | 12,000 |

```bash
python manage.py seed_everything --scale small        # a quick demo
python manage.py seed_everything --scale large        # load testing
python manage.py seed_everything --products 800       # override one number
```

The ratios matter. A catalogue of five products with three thousand reviews is
not a smaller version of production, it is a different shape — so the presets
move the numbers together.

---

## Commands

Run in this order if running individually. Each states plainly what it needs.

| Command | Creates | Needs |
|---|---|---|
| `seed_categories` | 20 categories, 152 subcategories | — |
| `seed_brands` | 15 brands | categories |
| `seed_catalog` | collections, base taxonomy | — |
| `seed_products` | products, variants, images, specs, attributes, tags | categories, brands |
| `seed_coupons` | 15 coupons across every type and state | categories |
| `seed_banners` | 8 banners across 6 placements | — |
| `seed_users` | customers with addresses | — |
| `seed_orders` | orders, items, history, shipments, payments, refunds | users, products |
| `seed_reviews` | reviews, review images, helpful votes | **delivered** orders |
| `seed_engagement` | wishlists, carts, notifications, preferences | users, products |
| `seed_recommendations` | browsing trails, affinities, homepage rails | products, orders |

```bash
python manage.py seed_everything --only seed_products,seed_reviews
python manage.py seed_everything --skip seed_orders
python manage.py seed_everything --flush          # destructive: clears first
```

---

## Idempotency

**Every command is safe to run repeatedly.** Verified across all 24 tables:
running `seed_everything` twice produces identical row counts.

This is harder than it sounds and three bugs had to be fixed to get there.
Worth knowing, because the same traps apply to any seeder added later:

1. **Identity must not come from a shared random stream.** Customer names were
   drawn from one `Random`, so on a second run index 7 got a different name, a
   different email, and therefore a brand-new account — cascading into
   duplicate addresses, wishlists and carts. Each customer now gets a `Random`
   seeded from its own index.

2. **An early return skips random draws.** The wishlist step returns early when
   a customer already has one, consuming no draws — which shifted the *next*
   decision (the cart coin flip) onto a different value. Each concern now has
   its own independent stream.

3. **Guard on the parent, not the child.** Carts were guarded on
   `cart.items.exists()`. A customer whose sampled products were all sold out
   got an empty cart, so the next run tried again and filled it. The guard is
   now on the cart existing at all.

Re-running is *additive up to the target*: seeding 500 products when 200 exist
creates 300 more. To start over, pass `--flush`.

---

## Images

Real photography from `seed_assets/`, never generated placeholders. Full setup
guide for the content team: [`seed_assets/README.md`](../seed_assets/README.md).

```
seed_assets/
├── products/<subcategory-slug>/    ← or products/_default/
├── banners/{hero,strip,category,sale}/
├── reviews/
├── brands/  categories/
└── manifest.json  or  manifest.csv   (optional, takes priority)
```

```bash
python manage.py seed_products --list-asset-folders   # what to populate
python manage.py seed_everything --assets-dir /mnt/photos/spring26
python manage.py seed_everything --fetch-remote       # allow http(s) manifests
python manage.py seed_everything --no-images          # skip imagery entirely
```

Nothing is written to the database as a path or URL. Files are copied into
`MEDIA_ROOT` through Django's normal upload machinery, so the API returns the
same absolute URLs it always has:

```json
"primary_image": {
  "image": "http://api.example.com/media/products/images/c35fce…jpg",
  "alt_text": "Everyday Chelsea Boots - front view",
  "is_primary": true
}
```

**With no assets present**, rows are still created and the image field is left
empty — the command prints which folders it looked in. It does not invent a
placeholder: a catalogue with visibly missing photography gets fixed, whereas
one full of grey rectangles is one everybody learns to ignore. If you genuinely
want stand-ins for a demo, ask explicitly with `--generate-placeholders`.

---

## What gets created, and why it looks like this

**Products** carry SKU, barcode, MRP, selling price, discount, gender,
material, season, occasion, pattern, fit, sleeve type and neck type. Prices
respect the `selling_price <= mrp` CHECK constraint.

**Variants** are 8–20 per product, sized from the category — a dress runs XS–XXL
across 2–3 colourways, a watch is one size across 8–15. A quarter of the grid is
deliberately out of stock so the "only 2 left" and "sold out" states have real
data behind them.

**Orders** span the full status spectrum, weighted the way real orders fall:
58% delivered, 8% cancelled, 2% returned, the rest in flight. Seeding only happy
paths leaves the cancellation and refund screens empty. Each order carries its
address snapshot, status history, and — where applicable — a shipment, a payment
and a refund.

Orders are written as model rows rather than through the checkout service. The
service reserves stock and enforces the state machine, which is right for a real
order and wrong for a fixture: it would drain the catalogue and refuse every
back-dated order.

**Reviews** are attached to **delivered order lines**, never to arbitrary
(user, product) pairs. `Review.order_item` is unique and
`is_verified_purchase` is only meaningful with a purchase behind it. Ratings are
skewed positive (52% five-star) the way real catalogue reviews are; a flat
distribution makes every product average three stars and the rating filter
useless. 86% are approved, the rest sit pending or rejected so the moderation
queue has work in it.

**Affinities** are not invented. `seed_recommendations` calls the existing
`rebuild_affinities` service, which derives edges from real order history —
fabricating them would put pairs on "frequently bought together" that nobody
has ever bought together, which is the one claim that rail may not make.

**Trending / best-seller / featured flags** are recomputed from the seeded
counters rather than assigned at random, so the homepage rails agree with the
products they promote.

---

## Demo accounts

`seed_users` creates customers with one shared password:

```
Password: Tr3ndz!Demo2026
Emails:   <first>.<last><n>@seed.fashiontrendz.local
```

The domain is non-routable, so demo mail cannot be delivered anywhere real.

**The command refuses to run when `ENVIRONMENT=production`.** Creating accounts
with a published password in production is handing out logins. Override with
`--allow-production` only if you are certain.

---

## Verified output at full scale

```
Categories           20        Orders             1,200
Subcategories       152        Order items        ~2,900
Brands               15        Shipments            ~860
Products            500        Payments           ~1,100
Product variants  ~6,993       Refunds              ~140
Product images    ~2,470       Reviews            3,000
Customers           200        Review images       ~540
Addresses           ~400       Wishlist items    ~1,200
Coupons              15        Recently viewed   ~8,000
Banners               8        Affinities          ~600
```

Per-product invariants, measured: images **min 4, max 6**; variants
**min 8, max 20**.

---

## Troubleshooting

| Message | Meaning |
|---|---|
| `No customers found. Run seed_users first.` | Pipeline order. Use `seed_everything`. |
| `No delivered orders found.` | `seed_reviews` ran before `seed_orders`. |
| `every delivered line is already reviewed` | Not an error — nothing left to do. |
| `no images found for products/<slug>/` | Drop files there or into `products/_default/`. |
| `Refusing to seed demo accounts … production` | Working guard. See above. |

A failed step leaves earlier steps in place; fix the cause and re-run, and the
completed work is skipped rather than repeated.
