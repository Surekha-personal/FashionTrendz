"""Wishlist permissions.

A wishlist belongs to exactly one account, so every endpoint requires
authentication. Guests get a client-side list until they sign in.
"""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.permissions import OwnerOnly

__all__ = ["IsAuthenticated", "OwnerOnly", "IsWishlistOwner"]


class IsWishlistOwner(OwnerOnly):
    """Allow access only to the owner of a wishlist or wishlist entry.

    A backstop. Every wishlist view resolves its queryset from
    ``request.user``, so a foreign row 404s before an object permission runs —
    which is the better failure, since a 403 would confirm the row exists.
    This catches the day a new view forgets that scoping.
    """

    message = "This wishlist does not belong to you."

    def has_object_permission(
        self, request: Request, view: APIView, obj: models.Model
    ) -> bool:
        """Resolve the owner through the wishlist when given an entry."""
        owner = getattr(obj, "user", None)
        if owner is None:
            wishlist = getattr(obj, "wishlist", None)
            owner = getattr(wishlist, "user", None)

        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and owner == user)
