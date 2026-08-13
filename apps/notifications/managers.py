"""Querysets and managers for the notifications module."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import models
from django.utils import timezone


class NotificationQuerySet(models.QuerySet):
    """Queries over notifications."""

    def for_user(self, user: Any) -> "NotificationQuerySet":
        """Restrict to one customer's notifications."""
        return self.filter(user=user)

    def inbox(self) -> "NotificationQuerySet":
        """Restrict to what the in-app bell icon shows.

        Email and SMS rows share this table as a delivery ledger; showing them
        in the inbox would double every event the customer sees.
        """
        from apps.notifications.models import NotificationChannel

        return self.filter(channel=NotificationChannel.IN_APP)

    def unread(self) -> "NotificationQuerySet":
        """Restrict to unread notifications."""
        return self.filter(is_read=False)

    def pending(self) -> "NotificationQuerySet":
        """Restrict to rows still waiting on a provider — the worker's read."""
        from apps.notifications.models import NotificationStatus

        return self.filter(status=NotificationStatus.PENDING)

    def failed(self) -> "NotificationQuerySet":
        """Restrict to deliveries that errored."""
        from apps.notifications.models import NotificationStatus

        return self.filter(status=NotificationStatus.FAILED)

    def retryable(self, max_attempts: int = 3) -> "NotificationQuerySet":
        """Failed deliveries still worth another attempt.

        Capped rather than retried forever: a permanently bad address fails
        identically every time, and an uncapped retry loop turns one dead
        mailbox into an endless queue.
        """
        from apps.notifications.models import NotificationStatus

        return self.filter(
            status=NotificationStatus.FAILED, attempts__lt=max_attempts
        )

    def on_channel(self, channel: str) -> "NotificationQuerySet":
        """Restrict to one delivery channel."""
        return self.filter(channel=channel)

    def of_event(self, event: str) -> "NotificationQuerySet":
        """Restrict to one event type."""
        return self.filter(event=event)

    def recent(self, days: int = 30) -> "NotificationQuerySet":
        """Restrict to the last ``days``."""
        return self.filter(created_at__gte=timezone.now() - timedelta(days=days))

    def stale(self, days: int = 180) -> "NotificationQuerySet":
        """Rows past their retention window — what the cleanup job prunes."""
        return self.filter(created_at__lt=timezone.now() - timedelta(days=days))

    def with_recipient(self) -> "NotificationQuerySet":
        """Join the recipient, which every delivery needs to address."""
        return self.select_related("user")


class NotificationPreferenceQuerySet(models.QuerySet):
    """Queries over notification preferences."""

    def opted_into_marketing(self) -> "NotificationPreferenceQuerySet":
        """Customers who still accept promotional messages."""
        return self.filter(marketing_enabled=True)

    def with_push_token(self) -> "NotificationPreferenceQuerySet":
        """Customers with a registered device."""
        return self.filter(push_enabled=True).exclude(push_token="")


NotificationManager = models.Manager.from_queryset(NotificationQuerySet)
NotificationPreferenceManager = models.Manager.from_queryset(
    NotificationPreferenceQuerySet
)
