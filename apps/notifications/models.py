"""Notification models.

Two tables. :class:`Notification` is one message to one person on one channel —
it is simultaneously the in-app inbox row and the delivery ledger for email,
SMS and push. :class:`NotificationPreference` is one row per customer holding
their opt-outs.

One table for both the inbox and the outbox is deliberate. Splitting them would
mean an in-app message and the email announcing the same event are separate
records that can disagree about whether the event happened, and every "did we
tell them?" question would have to check two places.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixins import BaseModel
from apps.notifications.managers import (
    NotificationManager,
    NotificationPreferenceManager,
)


class NotificationChannel(models.TextChoices):
    """How a notification reaches the customer."""

    IN_APP = "in_app", _("In-app")
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push")


class NotificationStatus(models.TextChoices):
    """Where a notification sits in its delivery lifecycle."""

    PENDING = "pending", _("Queued")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")
    # In-app rows are born delivered; there is nothing to hand to a provider.
    DELIVERED = "delivered", _("Delivered")


class NotificationCategory(models.TextChoices):
    """What kind of event produced this notification.

    Coarser than the event key on purpose: customers opt out of "marketing",
    not of "coupon_expiring". Transactional is deliberately absent from the
    preference model — a customer cannot unsubscribe from being told their
    order shipped.
    """

    ACCOUNT = "account", _("Account")
    ORDER = "order", _("Order")
    PAYMENT = "payment", _("Payment")
    REVIEW = "review", _("Review")
    MARKETING = "marketing", _("Marketing")
    SYSTEM = "system", _("System")


class Notification(BaseModel):
    """One message to one person on one channel."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("recipient"),
    )

    event = models.CharField(
        _("event"),
        max_length=64,
        db_index=True,
        help_text=_("Template key, e.g. order_shipped. See notifications/templates.py."),
    )
    category = models.CharField(
        _("category"),
        max_length=16,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
        db_index=True,
    )
    channel = models.CharField(
        _("channel"),
        max_length=8,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        db_index=True,
    )

    subject = models.CharField(_("subject"), max_length=200)
    body = models.TextField(_("body"))
    # Where the in-app notification navigates to when tapped. Relative, so it
    # survives the frontend moving domains.
    link = models.CharField(_("link"), max_length=255, blank=True)

    # Rendered context, kept for support: "what exactly did we tell them?"
    context = models.JSONField(_("context"), default=dict, blank=True)

    status = models.CharField(
        _("status"),
        max_length=12,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )
    is_read = models.BooleanField(_("read"), default=False, db_index=True)
    read_at = models.DateTimeField(_("read at"), null=True, blank=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)

    attempts = models.PositiveSmallIntegerField(_("delivery attempts"), default=0)
    error = models.CharField(_("last error"), max_length=255, blank=True)

    objects = NotificationManager()

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]
        indexes = [
            # The inbox read: this user's unread notifications, newest first.
            models.Index(
                fields=["user", "is_read", "-created_at"], name="notif_inbox_idx"
            ),
            # The queue worker's read.
            models.Index(fields=["status", "channel"], name="notif_queue_idx"),
            models.Index(fields=["event", "-created_at"], name="notif_event_idx"),
            # Serves the duplicate-suppression check in signals.py, which runs
            # on every payment and refund save. Without it that lookup scans.
            models.Index(fields=["user", "event"], name="notif_dedupe_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.event} to {self.user_id} via {self.channel}"

    @property
    def is_deliverable(self) -> bool:
        """Return whether this row still needs handing to a provider."""
        return self.status == NotificationStatus.PENDING


class NotificationPreference(BaseModel):
    """One customer's opt-outs.

    Booleans rather than a set of subscribed categories: a new notification type
    should reach everyone by default, and a subscription set means every
    existing customer silently misses it until they opt in to something they
    have never heard of.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preference",
        verbose_name=_("customer"),
    )

    email_enabled = models.BooleanField(_("email"), default=True)
    sms_enabled = models.BooleanField(_("SMS"), default=True)
    push_enabled = models.BooleanField(_("push"), default=True)

    # Marketing is the only category a customer may switch off wholesale.
    # Order and payment mail is transactional and stays on.
    marketing_enabled = models.BooleanField(_("marketing"), default=True)

    push_token = models.CharField(
        _("push token"),
        max_length=255,
        blank=True,
        help_text=_("Device token registered by the frontend."),
    )

    objects = NotificationPreferenceManager()

    class Meta:
        verbose_name = _("notification preference")
        verbose_name_plural = _("notification preferences")

    def __str__(self) -> str:
        return f"Notification preferences for {self.user_id}"

    def allows(self, channel: str, category: str) -> bool:
        """Return whether ``channel`` may carry a ``category`` message.

        One method rather than the caller reading four booleans, so the rule
        that marketing is opt-out-able and everything else is not lives in
        exactly one place.
        """
        if category == NotificationCategory.MARKETING and not self.marketing_enabled:
            return False

        return {
            NotificationChannel.EMAIL: self.email_enabled,
            NotificationChannel.SMS: self.sms_enabled,
            NotificationChannel.PUSH: self.push_enabled,
            # The in-app inbox is not a subscription; it is the account itself.
            NotificationChannel.IN_APP: True,
        }.get(channel, True)
