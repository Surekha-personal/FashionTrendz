"""Catalog permissions.

The catalogue is public read, staff write, which
:class:`apps.core.permissions.AdminOrReadOnly` already expresses — it is
re-exported rather than reimplemented. Only the rule that has no core
equivalent is defined here.
"""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.permissions import AdminOrReadOnly, IsAdmin, ReadOnly

__all__ = [
    "AdminOrReadOnly",
    "IsAdmin",
    "ReadOnly",
    "IsActiveOrStaff",
    "CatalogPermission",
]


class IsActiveOrStaff(BasePermission):
    """Hide deactivated catalogue rows from everyone except staff.

    A backstop, not the primary control. The public viewsets already filter
    ``is_active=True`` in ``get_queryset()``, so a deactivated row 404s before
    reaching an object permission — which is the better outcome, since a 403
    would confirm the row exists and let anyone enumerate unreleased categories
    by guessing slugs.

    This check exists for the case where a future view forgets that filter.
    """

    message = "This resource is not available."

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: models.Model,
    ) -> bool:
        """Return True for staff, or when the object is active."""
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.is_staff:
            return True
        return bool(getattr(obj, "is_active", True))


class CatalogPermission(BasePermission):
    """Public reads of active rows; staff-only writes.

    ``AdminOrReadOnly`` and ``IsActiveOrStaff`` combined into the single class
    the catalog viewsets use, so each viewset declares one permission instead of
    two that must be kept in the right order.
    """

    message = "Only administrators can modify the catalogue."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Allow safe methods for anyone; writes only for staff."""
        if request.method in SAFE_METHODS:
            return True
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: models.Model,
    ) -> bool:
        """Apply the method rule, then the active-row rule."""
        if not self.has_permission(request, view):
            return False
        return IsActiveOrStaff().has_object_permission(request, view, obj)
