"""Coupon permissions."""

from __future__ import annotations

from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.permissions import AdminOrReadOnly, IsAdmin

__all__ = ["IsAdmin", "AdminOrReadOnly", "CouponPermission"]


class CouponPermission(BasePermission):
    """Public reads of advertised offers; staff-only writes.

    Reads are open because the offers strip renders for signed-out visitors
    too. What the public read exposes is deliberately narrow: the viewset
    serves only ``Coupon.objects.public()``, so private influencer and goodwill
    codes are never listed even though anyone may read the endpoint.
    """

    message = "Only staff can manage coupons."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Allow safe methods for anyone; writes only for staff."""
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)
