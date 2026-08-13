"""Health checks.

Each check answers one question — is this dependency actually usable? — by
doing the smallest real operation against it. Nothing here reads configuration
and reports "looks fine": a correct connection string to a database that is out
of disk is exactly the failure a health check exists to catch.

Every check returns the same shape, so a monitor can consume them uniformly::

    {"name": ..., "ok": bool, "detail": str, "duration_ms": float}

Checks never raise. A health endpoint that 500s tells the monitor the app is
down when the truth may be that one optional dependency is degraded, and that
distinction is the entire value of the endpoint.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import time
from typing import Any, Callable

from django.conf import settings
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import connections
from django.utils import timezone

logger = logging.getLogger(__name__)

#: Written and deleted by the media check. Prefixed so it is obvious in a
#: bucket listing that nothing is meant to keep it.
PROBE_PREFIX = "healthcheck/probe"


def _timed(name: str, probe: Callable[[], str]) -> dict[str, Any]:
    """Run ``probe``, timing it and turning any exception into a failed check."""
    started = time.perf_counter()
    try:
        detail = probe()
        ok = True
    except Exception as exc:  # noqa: BLE001 - any failure is the same answer here
        detail = f"{type(exc).__name__}: {exc}"[:200]
        ok = False
        logger.warning("health check %s failed: %s", name, detail)

    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def check_database() -> dict[str, Any]:
    """Verify the database answers a query.

    ``SELECT 1`` rather than ``connection.ensure_connection()``: a pooled
    connection can be established and still be behind a failed-over primary
    that rejects statements.
    """

    def probe() -> str:
        connection = connections["default"]
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return f"{connection.vendor} reachable"

    return _timed("database", probe)


def check_cache() -> dict[str, Any]:
    """Verify the cache round-trips a value.

    Written *and read back*. A misconfigured cache backend silently accepts
    every write and returns None for every read, which looks healthy to a
    write-only check and breaks every cached endpoint.
    """

    def probe() -> str:
        key = f"healthcheck:{timezone.now().timestamp()}"
        token = "ok"
        cache.set(key, token, 30)
        value = cache.get(key)
        cache.delete(key)

        if value != token:
            raise RuntimeError("cache did not return what was written")
        return f"{settings.CACHES['default']['BACKEND'].rsplit('.', 1)[-1]} round-trip ok"

    return _timed("cache", probe)


def check_media_storage() -> dict[str, Any]:
    """Verify media storage accepts a write, a read and a delete.

    All three, because S3 credentials routinely carry PutObject without
    DeleteObject, and the first anyone hears of it is a bucket that only grows.
    """

    def probe() -> str:
        name = default_storage.save(
            f"{PROBE_PREFIX}-{int(time.time())}.txt", ContentFile(b"ok")
        )
        try:
            with default_storage.open(name) as handle:
                if handle.read().strip() != b"ok":
                    raise RuntimeError("storage returned unexpected content")
        finally:
            default_storage.delete(name)
        return f"{type(default_storage).__name__} writable"

    return _timed("media_storage", probe)


def check_email() -> dict[str, Any]:
    """Verify the mail backend opens a connection.

    Opened and closed without sending. A health check that sends mail is a
    health check that fills someone's inbox once a minute.
    """

    def probe() -> str:
        from django.core.mail import get_connection

        backend = get_connection(fail_silently=False)
        backend.open()
        backend.close()
        return f"{settings.EMAIL_BACKEND.rsplit('.', 2)[-2]} reachable"

    return _timed("email", probe)


def check_celery() -> dict[str, Any]:
    """Verify a Celery worker is alive and consuming.

    Pings the worker pool rather than the broker: a reachable broker with no
    worker attached is the common production failure, and it looks perfectly
    healthy from the broker's side.

    Reported as skipped rather than failed when no broker is configured — the
    application runs correctly without Celery, delivering notifications inline.
    """

    def probe() -> str:
        if not getattr(settings, "CELERY_BROKER_URL", ""):
            return "not configured (tasks run inline)"

        from config.celery import app

        replies = app.control.ping(timeout=2.0)
        if not replies:
            raise RuntimeError("no workers responded")
        return f"{len(replies)} worker(s) responding"

    return _timed("celery", probe)


def check_disk(minimum_free_mb: int = 500) -> dict[str, Any]:
    """Verify the media volume has room left.

    A full disk turns every image upload into a 500 long before it turns into
    an alert, so this check runs against ``MEDIA_ROOT`` specifically rather
    than the root filesystem.
    """

    def probe() -> str:
        usage = shutil.disk_usage(settings.MEDIA_ROOT if os.path.isdir(settings.MEDIA_ROOT) else "/")
        free_mb = usage.free // (1024 * 1024)
        if free_mb < minimum_free_mb:
            raise RuntimeError(f"only {free_mb} MB free")
        return f"{free_mb} MB free of {usage.total // (1024 * 1024)} MB"

    return _timed("disk", probe)


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------

#: Checks whose failure means the application cannot serve requests. A load
#: balancer should pull the instance out for these and only these — email being
#: down is a real problem, but it is not a reason to stop serving the catalogue.
CRITICAL_CHECKS: tuple[str, ...] = ("database", "cache")


def run_checks(*, deep: bool = False) -> dict[str, Any]:
    """Run the health checks and summarise them.

    ``deep`` adds the checks that touch external systems — storage, SMTP,
    Celery. They are excluded by default because this endpoint is polled every
    few seconds by a load balancer, and opening an SMTP connection that often
    is itself a problem.
    """
    checks = [check_database(), check_cache()]
    if deep:
        checks += [check_media_storage(), check_email(), check_celery(), check_disk()]

    failed = [check["name"] for check in checks if not check["ok"]]
    critical_failed = [name for name in failed if name in CRITICAL_CHECKS]

    return {
        "status": "unhealthy" if critical_failed else ("degraded" if failed else "healthy"),
        "healthy": not critical_failed,
        "checked_at": timezone.now().isoformat(),
        "failed": failed,
        "checks": checks,
    }


def application_status() -> dict[str, Any]:
    """Return what this build is and how it is configured.

    Deliberately free of secrets: hosts and connection strings are what an
    attacker wants from a status endpoint, so this reports whether things are
    configured, never with what.
    """
    return {
        "name": "Fashion Trendz API",
        "version": getattr(settings, "APP_VERSION", "1.0.0"),
        "environment": getattr(settings, "ENVIRONMENT", "development"),
        "debug": settings.DEBUG,
        "time": timezone.now().isoformat(),
        "timezone": settings.TIME_ZONE,
        "database": connections["default"].vendor,
        "cache": settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1],
        "celery_configured": bool(getattr(settings, "CELERY_BROKER_URL", "")),
        "email_configured": bool(settings.EMAIL_HOST) or settings.DEBUG,
        "storage": type(default_storage).__name__,
        "installed_apps": len(settings.INSTALLED_APPS),
    }


def system_information() -> dict[str, Any]:
    """Return the runtime this process is on.

    For support: "works on my machine" is usually a Python or platform
    difference, and this is the fastest way to see it.
    """
    import django

    return {
        "python": sys.version.split()[0],
        "django": django.get_version(),
        "platform": platform.platform(),
        "processor": platform.machine(),
        "hostname": platform.node(),
        "pid": os.getpid(),
        "cpu_count": os.cpu_count(),
    }
