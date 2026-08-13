"""Celery application.

Loaded by ``config/__init__.py`` so ``app.task`` decorators resolve wherever
Django is imported from — the web process, a worker, beat, or a management
command.

Everything configurable is read from Django settings with the ``CELERY_``
prefix, so there is one place to look for configuration rather than two.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("fashion_trendz")

# Settings live in Django, namespaced CELERY_*. Keeping them there means the
# same python-decouple environment plumbing configures the workers.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Finds tasks.py in every installed app.
app.autodiscover_tasks()


# ---------------------------------------------------------------------------
# Scheduled work
# ---------------------------------------------------------------------------
# Times are in the project timezone (Asia/Kolkata). The heavy jobs run in the
# small hours; the queue drain runs constantly because a delayed notification
# is a customer waiting.
app.conf.beat_schedule = {
    # -- Every few minutes ---------------------------------------------------
    "drain-notification-queue": {
        "task": "notifications.drain_queue",
        "schedule": crontab(minute="*/2"),
    },
    "retry-failed-notifications": {
        "task": "notifications.retry_failed",
        "schedule": crontab(minute="*/30"),
    },
    # -- Hourly --------------------------------------------------------------
    "expire-coupons": {
        "task": "core.expire_coupons",
        "schedule": crontab(minute=5),
    },
    "release-stale-payments": {
        "task": "core.release_stale_payments",
        "schedule": crontab(minute=15),
    },
    "warm-analytics-cache": {
        "task": "core.warm_analytics",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # -- Daily ---------------------------------------------------------------
    # 02:30 — after midnight orders have settled, before the morning traffic.
    "rebuild-recommendations": {
        "task": "core.rebuild_recommendations",
        "schedule": crontab(hour=2, minute=30),
    },
    "send-review-reminders": {
        "task": "core.send_review_reminders",
        "schedule": crontab(hour=10, minute=0),
    },
    "send-coupon-expiry-reminders": {
        "task": "core.send_coupon_expiry_reminders",
        "schedule": crontab(hour=10, minute=15),
    },
    "send-abandoned-cart-reminders": {
        "task": "core.send_abandoned_cart_reminders",
        "schedule": crontab(hour=11, minute=0),
    },
    "send-order-payment-reminders": {
        "task": "core.send_order_reminders",
        "schedule": crontab(hour=12, minute=0),
    },
    # -- Weekly --------------------------------------------------------------
    # Sunday 03:00. Retention work is the least urgent thing in the schedule
    # and the most disk-intensive, so it gets the quietest hour of the week.
    "purge-browsing-history": {
        "task": "core.purge_browsing_history",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    "purge-old-notifications": {
        "task": "notifications.purge_old",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),
    },
    "clean-abandoned-carts": {
        "task": "core.clean_abandoned_carts",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),
    },
}


@app.task(bind=True, name="celery.ping")
def ping(self) -> str:  # noqa: ANN001 - Celery supplies self
    """Return "pong". Used by the health check to prove a worker is alive.

    A scheduled task that never runs looks identical to one that runs and does
    nothing, so monitoring needs something it can call synchronously.
    """
    return "pong"
