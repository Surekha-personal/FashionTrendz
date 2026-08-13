# Deployment

Covers Docker, Nginx, Gunicorn and the release checklist.

---

## 1. Prerequisites

- Docker 24+ with Compose v2
- A domain with DNS pointing at the host
- TLS certificates (Let's Encrypt via certbot, or a load balancer terminating TLS)
- SMTP credentials
- Razorpay live keys plus a **separate** webhook secret

---

## 2. First deploy

```bash
git clone <repository> fashion-trendz && cd fashion-trendz

cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(50))"   # SECRET_KEY
```

Set at minimum:

```dotenv
SECRET_KEY=<generated>
DEBUG=False
ENVIRONMENT=production
ALLOWED_HOSTS=api.yourdomain.com
CSRF_TRUSTED_ORIGINS=https://api.yourdomain.com
CORS_ALLOWED_ORIGINS=https://yourdomain.com
FRONTEND_URL=https://yourdomain.com
DB_PASSWORD=<strong>
```

Then:

```bash
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_catalog
docker compose exec web python manage.py seed_products
```

Migrations run automatically — the entrypoint applies them, but **only in the
web container**. Workers and beat share the image and the entrypoint, and three
replicas racing to apply the same migration is how a deploy deadlocks on a
table lock.

Verify:

```bash
curl -fsS https://api.yourdomain.com/health/ | jq
docker compose ps                       # every service healthy
docker compose logs -f web worker beat
```

---

## 3. What runs

| Service | Purpose | Replicas |
|---|---|---|
| `postgres` | Database | 1 |
| `redis` | Cache, sessions, Celery broker | 1 |
| `web` | Gunicorn + Django | 1..n |
| `worker` | Celery worker | 1..n |
| `beat` | Celery scheduler | **exactly 1** |
| `nginx` | TLS termination, static/media, rate limiting | 1 |

`beat` must never be scaled. Two schedulers means every scheduled job fires
twice — including the ones that email customers.

---

## 4. Gunicorn

Tuning lives in `gunicorn.conf.py`, overridable per host:

| Variable | Default | Notes |
|---|---|---|
| `GUNICORN_WORKERS` | `(2 × cores) + 1` | IO-bound app; oversubscribing cores is intended |
| `GUNICORN_THREADS` | `2` | Cheap concurrency without monkey-patching psycopg2 |
| `GUNICORN_TIMEOUT` | `60` | Longer than the slowest endpoint (invoice PDF, CSV export) |
| `GUNICORN_MAX_REQUESTS` | `1000` | Recycles workers to cap memory growth |

`preload_app = True` — the app is imported once in the master and forked.
Saves memory through copy-on-write and turns import errors into a failed boot
rather than a failed request. The constraint it imposes: **nothing may open a
database connection at import time.**

---

## 5. Nginx

`docker/nginx.conf`. Three jobs:

1. **Buffer responses** (`proxy_buffering on`) so a slow client drains from
   Nginx rather than holding a Gunicorn worker open. The single most valuable
   line in the file.
2. **Serve `/static/` and `/media/` from disk.** A catalogue page requests
   dozens of images; routing those through Gunicorn occupies every worker
   serving bytes.
3. **Rate-limit before the application.** 20 r/s general, 2 r/s on credential
   endpoints. This is a second layer under DRF's throttles, not a replacement:
   Nginx stops traffic before it costs a worker; DRF knows what the request
   means.

`/health/` and `/ready/` are exempt from both limits and from the access log. A
rate-limited health check eventually returns 429 and takes the instance out of
rotation for being healthy.

### TLS

Terminate at a load balancer, or add certbot:

```bash
docker run --rm -v ./certs:/etc/letsencrypt certbot/certbot certonly \
  --standalone -d api.yourdomain.com
```

Mount `./certs` into the nginx service and add a `listen 443 ssl` server block.
With TLS terminated upstream, keep `SECURE_PROXY_SSL_HEADER` aligned with the
`X-Forwarded-Proto` header the proxy sets, or Django will redirect in a loop.

---

## 6. Static and media

Static files are collected **at image build time**, not at boot: it is
deterministic, it fails the build rather than the deploy, and every replica
ships identical hashed filenames. WhiteNoise serves them with the manifest
storage; Nginx serves them from the volume in front of that.

Media defaults to the `media` volume. For more than one host, set
`AWS_STORAGE_BUCKET_NAME` and the storage backend switches to S3 — no model
field, upload path or view is aware of the difference.

---

## 7. Release checklist

```bash
python manage.py check --deploy --fail-level ERROR
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py spectacular --validate
```

CI runs all four on every push (`.github/workflows/ci.yml`).

Before going live:

- [ ] `DEBUG=False`
- [ ] `SECRET_KEY` unique to this environment, not the one from `.env.example`
- [ ] `ALLOWED_HOSTS` lists exactly the real hostnames
- [ ] `ADMIN_URL` moved off `admin/` — drops the entire class of bots probing it
- [ ] `SECURE_SSL_REDIRECT=True`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- [ ] `SECURE_HSTS_SECONDS` set (start at 3600, raise to a year once confident)
- [ ] `CORS_ALLOWED_ORIGINS` is the storefront origin only, never `*`
- [ ] Razorpay **webhook** secret is the one from the dashboard's webhook page,
      not the API secret — using the wrong one fails every webhook silently
- [ ] Database backups scheduled and a restore tested
- [ ] `/health/?deep=true` green as a staff user

---

## 8. Zero-downtime updates

```bash
git pull
docker compose build web
docker compose up -d --no-deps --scale web=2 web    # new alongside old
docker compose up -d --no-deps --scale web=1 web    # retire the old
docker compose up -d --no-deps worker beat
```

Migrations must be backwards-compatible for the overlap window: add columns
nullable, backfill separately, drop in a later release. A migration that drops
a column the running replica still selects will 500 until the rollout finishes.

---

## 9. Backups

```bash
# Nightly
docker compose exec -T postgres pg_dump -U postgres fashion_trendz | gzip > backup-$(date +%F).sql.gz

# Restore
gunzip -c backup-2026-08-05.sql.gz | docker compose exec -T postgres psql -U postgres fashion_trendz
```

Back up the `media` volume too, unless media lives in S3. A database restore
without its images is a catalogue of broken links.

---

## 10. Troubleshooting

| Symptom | Cause |
|---|---|
| `web` restarts on boot | Database not ready, or a bad `DB_*` value. Check `docker compose logs postgres`. |
| Health check red on `cache` | `REDIS_URL` wrong or Redis unreachable. |
| Health check red on `celery` | Broker is up but no worker attached — the common production failure. |
| Notifications queue but never send | No worker consuming. `docker compose logs worker`. |
| Every scheduled job runs twice | More than one `beat` replica. |
| Static files 404 | `collectstatic` did not run in the build; rebuild without cache. |
| Webhooks all fail signature | Using the API secret instead of the webhook secret. |
| Infinite HTTPS redirect | `SECURE_PROXY_SSL_HEADER` does not match what the proxy sends. |
