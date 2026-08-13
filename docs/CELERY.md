# Redis and Celery

Redis is the cache, the session store and the Celery broker. Celery runs the
notification queue and every scheduled job.

**Both are optional.** With no `REDIS_URL` the cache falls back to in-memory and
notifications deliver inside the request. That is the correct configuration for
development and for the test suite, where a queued task nobody works is
indistinguishable from a bug. It is the wrong configuration for anything with
more than one worker process.

---

## Redis

```dotenv
REDIS_URL=redis://redis:6379/0          # cache and sessions
CELERY_BROKER_URL=redis://redis:6379/1  # queue
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

Separate databases so `FLUSHDB` on the cache cannot drop queued notifications.

### Why it matters beyond speed

LocMemCache is **per process**. Four Gunicorn workers on locmem hold four
different cached answers, and invalidating one leaves three stale. Everything
in the project that caches — catalogue payloads, rating summaries,
recommendation rails, the analytics dashboard — assumes invalidation actually
invalidates. Redis is what makes that true.

Sessions move to the cache when Redis is present. Guest carts and browsing
trails are keyed by session, so a database write on every anonymous page view
is the cheapest query in the project to delete.

### What is cached

| Key prefix | TTL | Invalidated by |
|---|---|---|
| `catalog:*` | 300s | Category/brand/collection save |
| `product:*` | 300s | Product save |
| `reviews:summary:*` | 900s | Any review status change |
| `reco:*` | 300s | TTL only |
| `recommendations:store_mean_rating` | 3600s | Any review write |
| `analytics:dashboard:*` | 900s | `warm_analytics`, or explicit invalidation |

---

## Celery

```bash
celery -A config worker --loglevel=info --concurrency=4
celery -A config beat   --loglevel=info
```

Under Compose both run automatically from the same image as the web container.
One image means one build, one dependency set, and no possibility of a task
importing code that only exists in the web image.

### Configuration

All Django settings, `CELERY_`-prefixed, so there is one place to look:

| Setting | Default | Why |
|---|---|---|
| `CELERY_TASK_ALWAYS_EAGER` | `True` when no broker | A `.delay()` that slips into a code path still executes rather than vanishing |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | `1` | Tasks are database-bound; prefetching means one slow task blocks the rest |
| `CELERY_WORKER_MAX_TASKS_PER_CHILD` | `500` | Long-lived Django processes leak connections |
| `CELERY_TASK_SOFT_TIME_LIMIT` | `600` | Raises inside the task so it can clean up |
| `CELERY_TASK_TIME_LIMIT` | `900` | Hard kill |

---

## The schedule

Defined in `config/celery.py`. Times are Asia/Kolkata.

| Task | When | Does |
|---|---|---|
| `notifications.drain_queue` | every 2 min | Delivers pending notifications |
| `notifications.retry_failed` | every 30 min | Re-attempts failures with attempts left |
| `core.expire_coupons` | hourly :05 | Deactivates coupons past their window |
| `core.release_stale_payments` | hourly :15 | Cancels abandoned payment intents (they hold stock) |
| `core.warm_analytics` | every 6 h | Recomputes the dashboard cache |
| `core.rebuild_recommendations` | 02:30 | Rebuilds the co-purchase graph |
| `core.send_review_reminders` | 10:00 | Asks about deliveries 5 days old |
| `core.send_coupon_expiry_reminders` | 10:15 | Warns holders 3 days out |
| `core.send_abandoned_cart_reminders` | 11:00 | Nudges signed-in customers |
| `core.send_order_reminders` | 12:00 | Chases unpaid orders |
| `core.purge_browsing_history` | Sun 03:00 | Retention, 90 days |
| `notifications.purge_old` | Sun 03:30 | Retention, 180 days |
| `core.clean_abandoned_carts` | Sun 04:00 | Deactivates 30-day-old carts |

The heavy jobs run in the small hours. The queue drain runs constantly because
a delayed notification is a customer waiting.

`beat` uses the default file-backed scheduler. The schedule lives in code, so
`django-celery-beat` would add a dependency, an app and a migration purely to
make it editable in the admin — which nobody has asked for.

---

## How notifications flow

```
services.notify(user, event, context)
  ├── renders the template
  ├── checks the customer's opt-outs
  ├── writes one Notification row per channel
  └── dispatches:
        no broker  → sends inline
        broker     → transaction.on_commit → send_notification_task.delay(id)
```

The `on_commit` matters. Handing a row id to a worker before the transaction
commits is a race the worker loses, and it is the classic way a task fires for
an order that then gets rolled back.

`drain_queue` every two minutes is the safety net: anything enqueued while the
broker was down, or dropped by a worker that died before `acks_late` could save
it, is still a pending row and gets picked up.

---

## Operating

```bash
celery -A config inspect ping           # workers alive?
celery -A config inspect active         # what is running
celery -A config inspect scheduled      # what is queued
celery -A config inspect stats

celery -A config call core.rebuild_recommendations    # run one now
celery -A config purge                                # drop the queue (destructive)
```

Or from the admin: **Notifications → Delivery ledger** shows every message and
its status, with *Resend selected*. `POST /api/v1/admin/notifications/drain/`
does the same over HTTP.

`/health/?deep=true` as a staff user pings the worker pool — not the broker. A
reachable broker with no worker attached is the common production failure, and
it looks perfectly healthy from the broker's side.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Notifications stay `pending` | No worker consuming. `celery -A config inspect ping`. |
| Every scheduled job runs twice | More than one `beat` replica. |
| Tasks run inline in production | `CELERY_BROKER_URL` unset, so `ALWAYS_EAGER` defaulted to `True`. |
| Worker memory grows | Lower `CELERY_WORKER_MAX_TASKS_PER_CHILD`. |
| `Received unregistered task` | Worker running an older image than the web container. Rebuild both. |
| Cache invalidation "not working" | Still on locmem. Check `/status/` reports `RedisCache`. |
