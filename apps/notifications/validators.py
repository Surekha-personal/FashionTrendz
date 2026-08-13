"""Validators for the notifications module."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Longest a push token may be. FCM tokens run to about 160 characters and
#: APNs to 64; 255 leaves room without letting the field become a text dump.
MAX_PUSH_TOKEN_LENGTH: int = 255

#: What a device token is allowed to contain. Providers issue URL-safe base64,
#: sometimes with a colon separator.
PUSH_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_:.\-]+$")


def validate_push_token(value: str) -> None:
    """Reject a device token that cannot be one.

    A token arrives from a client and is later interpolated into a provider
    request, so it is checked at the boundary rather than trusted because the
    frontend sent it.
    """
    token = (value or "").strip()
    if not token:
        return

    if len(token) > MAX_PUSH_TOKEN_LENGTH:
        raise ValidationError(
            _("That device token is too long."), code="push_token_too_long"
        )

    if not PUSH_TOKEN_PATTERN.match(token):
        raise ValidationError(
            _("That device token contains unexpected characters."),
            code="push_token_invalid",
        )


def validate_event_key(value: str) -> None:
    """Reject an event name with no template behind it.

    Called by the admin and by anything that lets a human type an event key. A
    notification for an unknown event renders to empty strings and is delivered
    blank, which is worse than being refused.
    """
    from apps.notifications.templates import TEMPLATES

    if value not in TEMPLATES:
        raise ValidationError(
            _("No notification template is registered for %(event)s."),
            code="unknown_event",
            params={"event": value},
        )
