"""Notification business logic.

The whole module has one entry point worth remembering: :func:`notify`. Give it
a user, an event key and a context dict; it renders the template, fans the
message out across the channels that event declares, respects the customer's
opt-outs, persists a row per channel, and delivers.

Everything else here is either a helper :func:`notify` uses or a queue
operation the Celery worker calls.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.notifications.channels import DeliveryError, get_channel
from apps.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from apps.notifications.templates import get_template

logger = logging.getLogger(__name__)

#: Attempts before a failed delivery is abandoned.
MAX_DELIVERY_ATTEMPTS: int = 3

#: How many rows one queue drain handles. A bound rather than "everything",
#: so a backlog is worked through in steady chunks instead of one task that
#: runs for an hour and dies holding the whole queue.
QUEUE_BATCH_SIZE: int = 200


def deliver_synchronously() -> bool:
    """Return whether notifications are delivered inside the request.

    True when no broker is configured — which is the case in development and in
    the test suite, where a queued notification that never gets worked is
    indistinguishable from a bug.
    """
    return not bool(getattr(settings, "CELERY_BROKER_URL", ""))


def get_preference(user: Any) -> NotificationPreference:
    """Return a customer's preferences, creating the default row on first use.

    Created lazily rather than by a signal on user creation: a signal would
    need a data migration for every account that predates it, and this is one
    query on a path that already touches the database.
    """
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    return preference


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def notify(
    user: Any,
    event: str,
    context: dict[str, Any] | None = None,
    *,
    channels: Iterable[str] | None = None,
    force: bool = False,
) -> list[Notification]:
    """Send ``event`` to ``user`` across the channels that event declares.

    ``channels`` narrows the fan-out for a caller that wants only one of them.
    ``force`` bypasses opt-outs and is for the rare message a customer cannot
    decline — currently only "your password changed", which is a security
    notice rather than a subscription.

    Returns the rows created, which is what tests assert on. Never raises for a
    delivery failure: a notification is a side effect of something that already
    happened, and losing an order because a mail server was down would be a far
    worse bug than a missing email.
    """
    if not _can_receive(user):
        return []

    template = get_template(event)
    payload = _build_context(user, context or {})
    rendered = template.render(payload)

    wanted = tuple(channels) if channels else template.channels
    preference = get_preference(user)

    created: list[Notification] = []
    for channel in wanted:
        if not force and not preference.allows(channel, template.category):
            continue
        created.append(
            _create(
                user=user,
                event=event,
                template_category=template.category,
                channel=channel,
                rendered=rendered,
                payload=payload,
            )
        )

    _dispatch(created)
    return created


def notify_many(
    users: Iterable[Any], event: str, context: dict[str, Any] | None = None
) -> int:
    """Send one event to many customers.

    Used by the scheduled jobs (coupon expiry, review reminders). Loops rather
    than bulk-creating because each recipient needs their own rendered context
    and their own opt-out check — and because the callers are batch jobs where
    a few hundred extra queries cost nothing anybody notices.
    """
    return sum(len(notify(user, event, context)) for user in users)


def _can_receive(user: Any) -> bool:
    """Return whether ``user`` is a real, active account we may contact."""
    return bool(
        user
        and getattr(user, "pk", None)
        and getattr(user, "is_active", False)
        and not getattr(user, "is_anonymous", False)
    )


def _build_context(user: Any, context: dict[str, Any]) -> dict[str, Any]:
    """Merge caller context with the values every template may reference.

    Recipient name and frontend URL are added here so no caller has to remember
    them, and so a template can use ``{first_name}`` unconditionally.
    """
    return {
        "first_name": (getattr(user, "first_name", "") or "there").strip() or "there",
        "email": getattr(user, "email", ""),
        "frontend_url": getattr(settings, "FRONTEND_URL", ""),
        **context,
    }


def _create(
    *,
    user: Any,
    event: str,
    template_category: str,
    channel: str,
    rendered: dict[str, str],
    payload: dict[str, Any],
) -> Notification:
    """Persist one notification row.

    SMS gets the template's short copy in ``body``; the row is the record of
    what was actually sent, and storing the long email text against an SMS
    would make the ledger lie.
    """
    body = rendered["sms"] if channel == NotificationChannel.SMS else rendered["body"]

    return Notification.objects.create(
        user=user,
        event=event,
        category=template_category,
        channel=channel,
        subject=rendered["subject"][:200],
        body=body,
        link=rendered["link"][:255],
        context=_jsonable(payload),
        status=NotificationStatus.PENDING,
    )


def _jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce a context dict into something ``JSONField`` will accept.

    Contexts routinely carry ``Decimal`` money and ``datetime`` timestamps.
    Stringifying anything exotic keeps the audit copy useful without making
    every caller pre-serialise.
    """
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        safe[key] = value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
    return safe


def _dispatch(notifications: list[Notification]) -> None:
    """Deliver now, or leave the rows for the queue worker.

    Delivery is pushed to ``transaction.on_commit`` when a broker is present:
    handing a row id to a worker before the transaction commits is a race the
    worker loses, and it is the classic way a task fires for an order that then
    gets rolled back.
    """
    if not notifications:
        return

    if deliver_synchronously():
        for notification in notifications:
            send_notification(notification)
        return

    ids = [notification.pk for notification in notifications]
    transaction.on_commit(lambda: _enqueue(ids))


def _enqueue(ids: list[int]) -> None:
    """Hand notification ids to the Celery worker.

    Imported inside the function so the notifications module stays importable
    on a machine with no Celery installed — the tests, and any developer who
    has not run ``pip install -r requirements.txt`` since this module landed.
    """
    try:
        from apps.notifications.tasks import send_notification_task
    except ImportError:  # pragma: no cover - Celery not installed
        logger.warning("celery unavailable, delivering %d notification(s) inline", len(ids))
        for notification in Notification.objects.filter(pk__in=ids):
            send_notification(notification)
        return

    for notification_id in ids:
        send_notification_task.delay(notification_id)


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def send_notification(notification: Notification) -> bool:
    """Hand one notification to its channel and record the outcome.

    Returns whether it was accepted. Failures are recorded on the row, not
    raised: the caller is either a signal handler or a queue worker, and
    neither has anything useful to do with the exception.
    """
    if notification.status in {NotificationStatus.SENT, NotificationStatus.DELIVERED}:
        return True

    try:
        channel = get_channel(notification.channel)
        if not channel.is_configured():
            raise DeliveryError(f"Channel {notification.channel} is not configured.")
        reference = channel.send(notification)
    except DeliveryError as exc:
        return _record_failure(notification, str(exc))
    except Exception as exc:  # noqa: BLE001 - a broken channel must not break the caller
        logger.exception("notification %s failed unexpectedly", notification.pk)
        return _record_failure(notification, str(exc))

    Notification.objects.filter(pk=notification.pk).update(
        status=(
            NotificationStatus.DELIVERED
            if notification.channel == NotificationChannel.IN_APP
            else NotificationStatus.SENT
        ),
        sent_at=timezone.now(),
        attempts=notification.attempts + 1,
        error="",
        updated_at=timezone.now(),
    )
    logger.info(
        "notification sent id=%s event=%s channel=%s ref=%s",
        notification.pk,
        notification.event,
        notification.channel,
        reference,
    )
    return True


def _record_failure(notification: Notification, error: str) -> bool:
    """Mark a delivery attempt as failed and keep the reason."""
    Notification.objects.filter(pk=notification.pk).update(
        status=NotificationStatus.FAILED,
        attempts=notification.attempts + 1,
        error=error[:255],
        updated_at=timezone.now(),
    )
    logger.warning(
        "notification failed id=%s event=%s channel=%s error=%s",
        notification.pk,
        notification.event,
        notification.channel,
        error[:120],
    )
    return False


def drain_queue(limit: int = QUEUE_BATCH_SIZE) -> dict[str, int]:
    """Deliver pending notifications. The queue worker's entry point."""
    pending = list(Notification.objects.pending().with_recipient()[:limit])
    sent = sum(1 for notification in pending if send_notification(notification))
    return {"processed": len(pending), "sent": sent, "failed": len(pending) - sent}


def retry_failed(limit: int = QUEUE_BATCH_SIZE) -> dict[str, int]:
    """Re-attempt failed deliveries that have not exhausted their attempts."""
    stuck = list(
        Notification.objects.retryable(MAX_DELIVERY_ATTEMPTS).with_recipient()[:limit]
    )
    for notification in stuck:
        notification.status = NotificationStatus.PENDING
    sent = sum(1 for notification in stuck if send_notification(notification))
    return {"processed": len(stuck), "sent": sent, "failed": len(stuck) - sent}


def purge_old(days: int = 180) -> int:
    """Delete notifications past their retention window.

    In-app rows older than six months are not an inbox, they are a table nobody
    reads. Delivery ledger rows age out with them.
    """
    return Notification.objects.stale(days).delete()[0]


# ---------------------------------------------------------------------------
# Inbox
# ---------------------------------------------------------------------------


def get_inbox(user: Any, *, unread_only: bool = False) -> QuerySet[Notification]:
    """Return the in-app notification list for one customer."""
    queryset = Notification.objects.for_user(user).inbox()
    return (queryset.unread() if unread_only else queryset).order_by("-created_at")


def unread_count(user: Any) -> int:
    """Return the number on the bell icon."""
    return Notification.objects.for_user(user).inbox().unread().count()


def mark_read(user: Any, uuid: str) -> bool:
    """Mark one notification read. Returns whether anything changed."""
    updated = (
        Notification.objects.for_user(user)
        .filter(uuid=uuid, is_read=False)
        .update(is_read=True, read_at=timezone.now(), updated_at=timezone.now())
    )
    return bool(updated)


def mark_all_read(user: Any) -> int:
    """Mark a customer's whole inbox read, in one ``UPDATE``."""
    return (
        Notification.objects.for_user(user)
        .inbox()
        .unread()
        .update(is_read=True, read_at=timezone.now(), updated_at=timezone.now())
    )


def delete_notification(user: Any, uuid: str) -> bool:
    """Remove one notification from a customer's inbox."""
    deleted, _ = Notification.objects.for_user(user).filter(uuid=uuid).delete()
    return bool(deleted)


def update_preference(user: Any, **fields: Any) -> NotificationPreference:
    """Update a customer's opt-outs.

    Only known fields are written, so a client sending an unexpected key gets
    its other changes applied rather than a 500.
    """
    preference = get_preference(user)
    allowed = {
        "email_enabled",
        "sms_enabled",
        "push_enabled",
        "marketing_enabled",
        "push_token",
    }

    changed = [key for key in fields if key in allowed]
    for key in changed:
        setattr(preference, key, fields[key])

    if changed:
        preference.save(update_fields=[*changed, "updated_at"])
    return preference


def get_stats() -> dict[str, Any]:
    """Return delivery counters for the admin dashboard."""
    from django.db.models import Count

    by_status = dict(
        Notification.objects.values_list("status").annotate(total=Count("id"))
    )
    by_channel = dict(
        Notification.objects.values_list("channel").annotate(total=Count("id"))
    )
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_channel": by_channel,
        "pending": by_status.get(NotificationStatus.PENDING, 0),
        "failed": by_status.get(NotificationStatus.FAILED, 0),
    }
