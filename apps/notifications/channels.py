"""Delivery channels.

One tiny class per channel behind a common ``send(notification) -> str`` call.
The abstraction exists because email is the only channel with a real provider
today; SMS and push have to be *pluggable* without the calling code changing,
and the way to guarantee that is to make the working channel go through the
same door as the stubs.

Backends are named in settings, so swapping the SMS stub for Twilio is one
environment variable and one class — no edit to the service layer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import EmailMessage
from django.utils.module_loading import import_string

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    """A provider refused or failed to accept a message."""


class BaseChannel:
    """The contract every channel implements."""

    #: Human name, used in logs and the admin.
    name: str = "base"

    def send(self, notification: "Notification") -> str:
        """Deliver ``notification`` and return a provider reference.

        Raise :class:`DeliveryError` on failure. Returning normally means the
        provider accepted it — not that the customer read it, which no channel
        can tell us.
        """
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Return whether this channel has what it needs to deliver.

        Checked before sending so an unconfigured provider produces one clear
        log line rather than a stack trace per notification.
        """
        return True


class InAppChannel(BaseChannel):
    """The in-app inbox.

    Delivery is the row already existing, so this does nothing and says so.
    Kept as a real channel rather than special-cased in the service, so the
    dispatch loop has no branch for it.
    """

    name = "in_app"

    def send(self, notification: "Notification") -> str:
        """Return immediately — the notification row *is* the delivery."""
        return f"inapp:{notification.pk}"


class EmailChannel(BaseChannel):
    """SMTP email via Django's configured backend."""

    name = "email"

    def is_configured(self) -> bool:
        """Return whether a backend is set.

        The console backend counts as configured: in development, printing to
        stdout is the intended delivery.
        """
        return bool(getattr(settings, "EMAIL_BACKEND", ""))

    def send(self, notification: "Notification") -> str:
        """Send one email, raising :class:`DeliveryError` on any SMTP problem."""
        recipient = (notification.user.email or "").strip()
        if not recipient:
            raise DeliveryError("Recipient has no email address.")

        try:
            message = EmailMessage(
                subject=notification.subject,
                body=notification.body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient],
            )
            sent = message.send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - every SMTP error is the same failure
            raise DeliveryError(str(exc)[:250]) from exc

        if not sent:
            raise DeliveryError("The mail backend accepted nothing.")
        return f"email:{recipient}"


class ConsoleSMSChannel(BaseChannel):
    """SMS placeholder that logs instead of sending.

    The default. It keeps every SMS-carrying flow exercisable end to end —
    including in tests — without an account, a per-message charge, or a real
    phone number in a fixture. Swap it for a provider by setting
    ``SMS_BACKEND``; the interface is the one method above.
    """

    name = "sms"

    def send(self, notification: "Notification") -> str:
        """Log the message that a provider would have sent."""
        number = _mobile_for(notification.user)
        if not number:
            raise DeliveryError("Recipient has no mobile number.")

        logger.info(
            "sms to=%s event=%s body=%s",
            number,
            notification.event,
            notification.body[:160],
        )
        return f"sms:{number}"


class ConsolePushChannel(BaseChannel):
    """Push placeholder that logs instead of sending.

    Same reasoning as the SMS stub. A real implementation (FCM, APNs) reads
    ``NotificationPreference.push_token`` and posts to the provider.
    """

    name = "push"

    def send(self, notification: "Notification") -> str:
        """Log the payload that a push provider would have received."""
        token = _push_token_for(notification.user)
        if not token:
            raise DeliveryError("Recipient has no registered device.")

        logger.info(
            "push token=%s… event=%s title=%s",
            token[:12],
            notification.event,
            notification.subject,
        )
        return f"push:{token[:12]}"


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

#: Fallbacks used when settings name no backend.
DEFAULT_BACKENDS: dict[str, str] = {
    "in_app": "apps.notifications.channels.InAppChannel",
    "email": "apps.notifications.channels.EmailChannel",
    "sms": "apps.notifications.channels.ConsoleSMSChannel",
    "push": "apps.notifications.channels.ConsolePushChannel",
}

#: Settings name per channel, so each is overridable independently.
BACKEND_SETTINGS: dict[str, str] = {
    "in_app": "NOTIFICATION_INAPP_BACKEND",
    "email": "NOTIFICATION_EMAIL_BACKEND",
    "sms": "SMS_BACKEND",
    "push": "PUSH_BACKEND",
}

_cache: dict[str, BaseChannel] = {}


def get_channel(channel: str) -> BaseChannel:
    """Return the backend instance for ``channel``.

    Instances are cached per process: they are stateless, and importing a
    dotted path on every notification is measurable when a bulk send fans out
    over thousands of rows.
    """
    if channel in _cache:
        return _cache[channel]

    path = getattr(
        settings, BACKEND_SETTINGS.get(channel, ""), ""
    ) or DEFAULT_BACKENDS.get(channel)
    if not path:
        raise DeliveryError(f"No backend configured for channel {channel!r}.")

    instance = import_string(path)()
    _cache[channel] = instance
    return instance


def reset_channel_cache() -> None:
    """Forget resolved backends.

    Needed by tests that override a backend setting after something has already
    resolved the default.
    """
    _cache.clear()


def _mobile_for(user: Any) -> str:
    """Return the customer's mobile number.

    The account's own number first, falling back to the default shipping
    address. Most customers never fill in the profile field but every customer
    who has ordered has given a delivery number.
    """
    own = (getattr(user, "mobile_number", "") or "").strip()
    if own:
        return own

    address = getattr(user, "default_address", None)
    return (getattr(address, "mobile", "") or "").strip()


def _push_token_for(user: Any) -> str:
    """Return the customer's registered device token, if any."""
    preference = getattr(user, "notification_preference", None)
    return (getattr(preference, "push_token", "") or "").strip()
