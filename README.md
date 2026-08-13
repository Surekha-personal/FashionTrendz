# Fashion Trendz — Backend API

Production Django REST backend for the Fashion Trendz ecommerce platform. Serves
a Next.js 15 storefront: catalogue, cart, checkout, payments, reviews,
recommendations, notifications and an admin analytics surface.

**Stack** — Python 3.14 · Django 6.0 · Django REST Framework · PostgreSQL 18 ·
Redis · Celery · JWT · drf-spectacular

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                                  # then set SECRET_KEY and DB_*
createdb fashion_trendz

python manage.py migrate
python manage.py seed_catalog                         # categories, subcategories, 50 brands
python manage.py seed_products                        # 700+ products with variants
python manage.py createsuperuser
python manage.py runserver
```

Nothing above needs Redis or Celery. Without a broker the cache is in-memory and
notifications deliver inside the request — correct for development, wrong for
more than one worker. See [docs/CELERY.md](docs/CELERY.md).

| URL | What |
|---|---|
| `/api/v1/` | The API |
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc |
| `/api/schema/` | OpenAPI 3 |
| `/health/` `/ready/` | Probes (public) |
| `/admin/` | Django admin |

---

## Architecture

Twelve apps under `apps/`, each with the same shape. The rule that holds
everywhere: **views are thin, business logic lives in `services.py`.** A view
parses input, calls one service function and serialises the result.

```
config/          settings.py · urls.py · celery.py · wsgi.py · asgi.py
apps/
  core/          Envelope renderer, exception handler, pagination, permissions,
                 throttling, mixins, validators, middleware, health checks,
                 cross-cutting scheduled tasks
  users/         Custom user, JWT auth, addresses
  catalog/       Categories, subcategories, brands, collections
  products/      Products, variants, images, search, filters, facets
  wishlist/      Saved products
  cart/          Guest and authenticated bags, money calculation
  orders/        Checkout, order state machine, shipments, invoice PDFs
  coupons/       Coupon rules, validation, usage ledger
  payments/      Gateway abstraction (Razorpay live), webhooks, refunds
  reviews/       Verified-purchase reviews, moderation, ratings
  recommendations/ Browsing trail, trending score, co-purchase graph, 8 rails
  notifications/ Email · SMS · push · in-app, templates, delivery ledger
  analytics/     Dashboard aggregates, 8 CSV reports (no models)
```

Per-app files: `models.py` `managers.py` `services.py` `serializers.py`
`views.py` `urls.py` `permissions.py` `validators.py` `signals.py` `admin.py`
`tests.py` `migrations/`.

### Conventions

- **Response envelope** — every response is `{success, message, data}` or
  `{success, message, errors}`, applied at render time by
  `core.renderers.EnvelopeJSONRenderer`. Monitoring endpoints are the one
  exception; probes should not have to parse an envelope.
- **UUID as public id, `BigAutoField` as primary key** — UUIDs in URLs, integers
  in indexes.
- **Money is `Decimal`, serialised as a string.** Never a float.
- **Snapshots** — orders freeze product, address and price so history cannot be
  rewritten by a catalogue edit.
- **Denormalised counters** maintained with `F()` expressions, with a recount
  service for repair.
- **Database constraints over application checks** for anything a concurrent
  request could race.

---

## API summary

All routes are under `/api/v1/`. Full schema at `/api/docs/`.

| Area | Routes |
|---|---|
| Auth | `auth/register` `auth/login` `auth/logout` `auth/refresh` `auth/password/*` `auth/profile` `auth/addresses` |
| Catalog | `categories` `subcategories` `brands` `collections` |
| Products | `products` `products/{slug}` `products/search` `products/facets` `products/homepage` |
| Wishlist | `wishlist` `wishlist/toggle` `wishlist/move-to-cart` |
| Cart | `cart` `cart/add` `cart/update` `cart/remove` `cart/merge` `cart/summary` |
| Orders | `orders` `orders/{number}` `orders/checkout` `orders/{number}/cancel` `orders/{number}/invoice` |
| Coupons | `coupons` `coupons/validate` `coupons/apply` |
| Payments | `payments/create` `payments/verify` `payments/webhook/{gateway}` `refunds` |
| Reviews | `products/{slug}/reviews` `.../summary` `.../gallery` `reviews` `reviews/{uuid}/helpful` |
| Recommendations | `recommendations/trending` `.../for-you` `.../products/{slug}/related` `recently-viewed` |
| Notifications | `notifications` `notifications/unread-count` `notifications/preferences` |
| Admin | `admin/dashboard/*` `admin/analytics/*` `admin/reports/*` `admin/reviews` `admin/notifications` |
| Monitoring | `/health/` `/ready/` `/status/` `/system/` (root, unversioned) |

---

## Testing

```bash
python manage.py test                     # everything
python manage.py test apps.orders         # one module
python manage.py test --parallel 4        # faster; suppresses tracebacks
python manage.py makemigrations --check --dry-run   # migration drift
python manage.py spectacular --validate   # schema
```

---

## Deployment

```bash
docker compose up -d --build
```

Full walkthrough in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Environment
reference in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md). Queue and cache in
[docs/CELERY.md](docs/CELERY.md).

---

## Operational commands

```bash
python manage.py seed_catalog                        # taxonomy and brands
python manage.py seed_products                       # 700+ products
python manage.py rebuild_affinities                  # co-purchase graph (nightly)
python manage.py purge_browsing_history --days 90    # retention (weekly)
```

Under Celery these run on the beat schedule in `config/celery.py`. The
management commands remain for manual runs and for hosts without a worker.
