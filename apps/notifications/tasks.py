"""Celery tasks for the notifications module.

Every task is a thin wrapper over a service function. The task decides
*retries and logging*; the service decides *what happens*. That split is what
lets the same work run from a management shell, an admin action, or the queue,
and behave identically in all three.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import shared_task

from apps.notifications import services

logger = logging.getLogger(__name__)


@shared_task(
    name="notifications.send",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def send_notification_task(self: Any, notification_id: int) -> bool:
    """Deliver one notification.

    ``acks_late`` so a worker killed mid-send leaves the message on the broker
    and another worker picks it up — the failure mode of a lost notification is
    better than the failure mode of a lost acknowledgement.

    A row that has vanished is not an error: the customer deleted it, or the
    account was closed, between enqueue and delivery.
    """
    from apps.notifications.models import Notification

    notification = (
        Notification.objects.select_related("user").filter(pk=notification_id).first()
    )
    if notification is None:
        logger.info("notification %s no longer exists, skipping", notification_id)
        return False

    return services.send_notification(notification)


@shared_task(name="notifications.drain_queue")
def drain_queue_task(limit: int = services.QUEUE_BATCH_SIZE) -> dict[str, int]:
    """Deliver whatever is pending.

    The safety net under :func:`send_notification_task`. Anything enqueued
    while the broker was down, or dropped by a worker that died before
    ``acks_late`` could save it, is still a pending row and gets picked up
    here within two minutes.
    """
    result = services.drain_queue(limit)
    if result["processed"]:
        logger.info("notification queue drained: %s", result)
    return result


@shared_task(name="notifications.retry_failed")
def retry_failed_task(limit: int = services.QUEUE_BATCH_SIZE) -> dict[str, int]:
    """Re-attempt failed deliveries that have attempts remaining."""
    result = services.retry_failed(limit)
    if result["processed"]:
        logger.info("failed notifications retried: %s", result)
    return result


@shared_task(name="notifications.purge_old")
def purge_old_task(days: int = 180) -> int:
    """Delete notifications past their retention window."""
    removed = services.purge_old(days)
    logger.info("purged %d notification(s) older than %d days", removed, days)
    return removed
