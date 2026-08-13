"""Order permissions.

An order is the most sensitive object in the system — it carries a home
address, a phone number and a purchase history. Access is therefore resolved
from ``request.user``, never from a client-supplied identifier, and staff are
the only accounts that see anyone else's.
"""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.permissions import IsAdmin, OwnerOrAdmin

__all__ = ["IsAuthenticated", "IsAdmin", "OwnerOrAdmin", "IsOrderOwner", "CanManageOrders"]


class IsOrderOwner(OwnerOrAdmin):
    """Allow the customer who placed the order, or any staff account.

    A backstop. Every order view scopes its queryset by ``request.user``, so a
    stranger's order number yields 404 rather than 403 — which matters here
    more than anywhere else in the project, because a 403 would confirm that a
    guessed order number is real.
    """

    message = "This order does not belong to you."

    def has_object_permission(
        self, request: Request, view: APIView, obj: models.Model
    ) -> bool:
        """Resolve the owner through the order when given a line or shipment."""
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        if user.is_staff:
            return True

        owner = getattr(obj, "user", None)
        if owner is None:
            order = getattr(obj, "order", None)
            owner = getattr(order, "user", None)

        return owner == user


class CanManageOrders(IsAdmin):
    """Allow only staff to change fulfilment state.

    Separate from :class:`IsOrderOwner` because the two answer different
    questions: a customer may cancel their own order, but only staff may mark
    it packed, shipped or delivered. Today both require ``is_staff``; when a
    warehouse role exists, only this class changes.
    """

    message = "Only staff can update order fulfilment."
