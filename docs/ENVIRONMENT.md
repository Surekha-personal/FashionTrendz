# Environment variables

Every environment-specific value is read through python-decouple from the
process environment or `.env`. There is no dev/prod settings split: one module,
one set of keys, behaviour switched by `DEBUG` and overridable per key.

`.env.example` is the template. Copy it, fill in the blanks, never commit it
filled.

---

## Required

Nothing starts without these.

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Unique per environment. `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DB_NAME` `DB_USER` `DB_PASSWORD` | PostgreSQL credentials |

---

## Core

| Variable | Default | Notes |
|---|---|---|
| `DEBUG` | `False` | Never `True` in production |
| `ENVIRONMENT` | `development` | Reported by `/status/`; nothing branches on it |
| `APP_VERSION` | `1.0.0` | Reported by `/status/` |
| `ALLOWED_HOSTS` | *(empty)* | Comma-separated. Exactly the real hostnames |
| `CSRF_TRUSTED_ORIGINS` | *(empty)* | Full origins with scheme |
| `ADMIN_URL` | `admin/` | **Change it.** Drops the entire class of bots probing `/admin/` |
| `FRONTEND_URL` | `http://localhost:3000` | Used in email links |

## Database

Two ways to configure it. `DATABASE_URL` wins outright when set; the discrete
`DB_*` keys are the fallback for a local or self-hosted server.

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | *(empty)* | Full DSN from a managed provider (Neon, Supabase, RDS, Render). Overrides every `DB_*` value below |

A `-pooler` hostname is detected automatically and switches two things off,
because both break behind PgBouncer in transaction mode:

- `CONN_MAX_AGE` drops to `0` — Django's own connection reuse fights the
  external pool for the same sockets, and a persistent connection holds a
  pooled slot open per worker.
- `DISABLE_SERVER_SIDE_CURSORS` is set — a server-side cursor outlives the
  transaction that owns it, which transaction pooling cannot honour.

Query parameters in the DSN are passed through to libpq untouched, so
provider-specific flags such as Neon's `channel_binding=require` reach the
driver rather than being dropped.

| Variable | Default |
|---|---|
| `DB_HOST` | `localhost` |
| `DB_PORT` | `5432` |
| `DB_CONN_MAX_AGE` | `60` |
| `DB_CONNECT_TIMEOUT` | `10` |
| `DB_SSLMODE` | `prefer` — set `require` for a managed database |

## Cache, queue

| Variable | Default | Notes |
|---|---|---|
| `REDIS_URL` | *(empty)* | Empty ⇒ in-memory cache. **Set it for >1 worker** |
| `CELERY_BROKER_URL` | `REDIS_URL` | Empty ⇒ tasks run inline |
| `CELERY_RESULT_BACKEND` | broker | |
| `CACHE_KEY_PREFIX` | `ft` | Namespaces a shared Redis |
| `CACHE_DEFAULT_TIMEOUT` | `300` | |
| `CELERY_PREFETCH` | `1` | |
| `CELERY_MAX_TASKS_PER_CHILD` | `500` | |
| `CELERY_SOFT_TIME_LIMIT` / `CELERY_TIME_LIMIT` | `600` / `900` | |

## Email

| Variable | Default | Notes |
|---|---|---|
| `EMAIL_BACKEND` | console when `DEBUG`, SMTP otherwise | |
| `EMAIL_HOST` `EMAIL_PORT` `EMAIL_HOST_USER` `EMAIL_HOST_PASSWORD` | | |
| `EMAIL_USE_TLS` | `True` | |
| `DEFAULT_FROM_EMAIL` | `Fashion Trendz <no-reply@…>` | |
| `PASSWORD_RESET_TIMEOUT` | `86400` | Seconds |

## Notifications

| Variable | Default | Notes |
|---|---|---|
| `SMS_BACKEND` | `…ConsoleSMSChannel` | Logs instead of sending. Swap for a provider class |
| `PUSH_BACKEND` | `…ConsolePushChannel` | Same |
| `NOTIFICATION_RETENTION_DAYS` | `180` | |

Both stubs implement `send(notification) -> str`. Replacing one is a class plus
an environment variable — no service-layer change.

## Payments

| Variable | Notes |
|---|---|
| `PAYMENT_DEFAULT_GATEWAY` | `razorpay` |
| `RAZORPAY_KEY_ID` `RAZORPAY_KEY_SECRET` | API credentials |
| `RAZORPAY_WEBHOOK_SECRET` | **A different secret**, from the dashboard's webhook page. Using the API secret means every webhook fails signature verification, silently |

## Object storage

Leave `AWS_STORAGE_BUCKET_NAME` blank for local disk. Setting it switches the
default file storage to S3 and nothing else changes.

| Variable | Default |
|---|---|
| `AWS_STORAGE_BUCKET_NAME` | *(empty)* |
| `AWS_ACCESS_KEY_ID` `AWS_SECRET_ACCESS_KEY` | |
| `AWS_S3_REGION_NAME` | `ap-south-1` |
| `AWS_S3_ENDPOINT_URL` | *(empty)* — set for Spaces, R2, MinIO |
| `AWS_S3_CUSTOM_DOMAIN` | *(empty)* — CDN hostname |

## Security

All default to secure when `DEBUG=False`.

| Variable | Production |
|---|---|
| `SECURE_SSL_REDIRECT` | `True` |
| `SECURE_HSTS_SECONDS` | Start `3600`, raise to `31536000` once confident |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` `SECURE_HSTS_PRELOAD` | `True` |
| `SESSION_COOKIE_SECURE` `CSRF_COOKIE_SECURE` | `True` |
| `CORS_ALLOWED_ORIGINS` | Storefront origin only. Never `*` |
| `CORS_ALLOW_CREDENTIALS` | `True` |

## Throttling

| Variable | Default | Applies to |
|---|---|---|
| `THROTTLE_ANON` | `100/hour` | Anonymous |
| `THROTTLE_USER` | `1000/hour` | Authenticated |
| `THROTTLE_LOGIN` | `10/min` | Login (IP) |
| `THROTTLE_REGISTER` | `10/hour` | Registration (IP) |
| `THROTTLE_PASSWORD_RESET` | `5/hour` | Reset (IP) |
| `THROTTLE_CHECKOUT` | `30/hour` | Checkout (user) |
| `THROTTLE_BURST` | `60/min` | Short-window companion |
| `THROTTLE_ANALYTICS` | `120/hour` | Admin dashboard |
| `THROTTLE_REPORT` | `30/hour` | CSV exports |
| `THROTTLE_NOTIFICATION_QUEUE` | `20/hour` | Manual queue drain/retry |
| `THROTTLE_PRODUCT_VIEW` | `600/hour` | Recording browsing history |

## Business rules

| Variable | Default |
|---|---|
| `CART_FREE_SHIPPING_THRESHOLD` | `999.00` |
| `CATALOG_CACHE_TTL` `PRODUCT_CACHE_TTL` `RECOMMENDATION_CACHE_TTL` | `300` |
| `REVIEW_AUTO_APPROVE` | `False` — only enable if nobody drains the queue |
| `MAX_RECENTLY_VIEWED` | `30` |
| `TRENDING_WEIGHT_VIEW` | `1.0` |
| `TRENDING_WEIGHT_PURCHASE` | `3.0` |
| `TRENDING_WEIGHT_WISHLIST` | `2.0` |
| `TRENDING_WEIGHT_REVIEW` | `1.5` |
| `TRENDING_WEIGHT_RATING` | `2.0` |
| `TRENDING_WEIGHT_RECENCY` | `4.0` |
| `TRENDING_HALF_LIFE_DAYS` | `30` |
| `TRENDING_RATING_PRIOR` | `10` |

The trending weights are documented in full in
`apps/recommendations/scoring.py`. Read that before changing any of them.

## Gunicorn

| Variable | Default |
|---|---|
| `GUNICORN_BIND` | `0.0.0.0:8000` |
| `GUNICORN_WORKERS` | `(2 × cores) + 1` |
| `GUNICORN_THREADS` | `2` |
| `GUNICORN_TIMEOUT` | `60` |
| `GUNICORN_MAX_REQUESTS` | `1000` |
| `GUNICORN_LOG_LEVEL` | `info` |

---

## Verifying

```bash
python manage.py check --deploy --fail-level ERROR
curl -s localhost:8000/status/ -H "Authorization: Bearer <staff-jwt>" | jq
```

`/status/` reports whether each dependency is configured, never with what. It
is deliberately free of secrets — hosts and connection strings are exactly what
an attacker wants from a status endpoint.
