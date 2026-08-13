"""Cart permissions.

Unlike the wishlist, the cart is open to guests — blocking anonymous shoppers
from a bag is the fastest way to lose the sale. Ownership is enforced by
resolving the cart from the request (user or session), never from a client-
supplied id, so there is no cart a caller can name that is not already theirs.
"""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

__all__ = ["AllowAny", "CartAccessPermission", "IsCartOwner"]


class CartAccessPermission(BasePermission):
    """Allow anyone to hold a cart.

    Deliberately permissive. The security property comes from resolution, not
    from this class: :func:`apps.cart.services.get_or_create_cart` derives the
    cart from ``request.user`` or the session key, so a caller can only ever
    reach their own. An endpoint taking a cart id from the body would need a
    real object check — which is precisely why none of them do.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Allow every caller, authenticated or not."""
        return True


class IsCartOwner(BasePermission):
    """Allow access only to the owner of a cart or cart line.

    A backstop for any future view that does take an identifier. Matches on the
    signed-in user, or on the session key for a guest cart.
    """

    message = "This cart does not belong to you."

    def has_object_permission(
        self, request: Request, view: APIView, obj: models.Model
    ) -> bool:
        """Return True when the request owns the cart behind ``obj``."""
        cart = obj if hasattr(obj, "session_key") else getattr(obj, "cart", None)
        if cart is None:
            return False

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return cart.user_id == user.pk

        session_key = getattr(request.session, "session_key", None)
        return bool(
            session_key and cart.user_id is None and cart.session_key == session_key
        )
