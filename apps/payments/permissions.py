"""Payment permissions."""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.permissions import IsAdmin

__all__ = ["IsAuthenticated", "IsAdmin", "AllowAny", "IsPaymentOwner", "WebhookPermission"]


class IsPaymentOwner(BasePermission):
    """Allow the customer who placed the order, or any staff account."""

    message = "This payment does not belong to you."

    def has_object_permission(
        self, request: Request, view: APIView, obj: models.Model
    ) -> bool:
        """Resolve the owner through the payment's order."""
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if user.is_staff:
            return True

        order = getattr(obj, "order", None) or getattr(
            getattr(obj, "payment", None), "order", None
        )
        return bool(order and order.user_id == user.pk)


class WebhookPermission(BasePermission):
    """Allow any caller to POST a webhook.

    Deliberately open, and safe for one reason: **the signature is the
    authentication.** Gateways call from rotating IP ranges with no credentials
    we control, so there is nothing to authenticate against — the HMAC over the
    raw body, checked with ``compare_digest``, is what proves the request came
    from the provider.

    Requiring a session or token here would simply break the integration while
    adding no security the signature does not already give.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Allow the request through to signature verification."""
        return True
