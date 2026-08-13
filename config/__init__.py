"""Project package.

Imports the Celery application so ``@shared_task`` decorators bind to it
however Django is started.

Guarded, because Celery is a deployment dependency rather than a language one:
a developer running the test suite on a fresh checkout, or a CI job that
installs no broker, should not be stopped by a missing import. Absent Celery,
:func:`apps.notifications.services.deliver_synchronously` returns True and
everything the queue would have done happens inline.
"""

from __future__ import annotations

try:
    from config.celery import app as celery_app
except ImportError:  # pragma: no cover - Celery not installed
    celery_app = None  # type: ignore[assignment]

__all__ = ("celery_app",)
