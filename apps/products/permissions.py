"""Product permissions.

The catalogue is public read, staff write — the same rule the catalog module
established. :class:`apps.catalog.permissions.CatalogPermission` already
expresses it exactly, so it is re-exported rather than reimplemented.
"""

from __future__ import annotations

from django.db import models
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.catalog.permissions import CatalogPermission
from apps.core.permissions import AdminOrReadOnly, IsAdmin, ReadOnly

__all__ = [
    "CatalogPermission",
    "AdminOrReadOnly",
    "IsAdmin",
    "ReadOnly",
    "ProductPermission",
    "CanManageInventory",
]

#: Products follow the catalogue rule exactly. Aliased for readability at the
#: call site — a viewset declaring ``ProductPermission`` reads better than one
#: declaring ``CatalogPermission``.
ProductPermission = CatalogPermission


class CanManageInventory(BasePermission):
    """Allow stock adjustments only to staff.

    Separate from :class:`ProductPermission` because inventory is the one part
    of the catalogue that a warehouse role should be able to change without
    being able to rewrite prices and descriptions. Today both require
    ``is_staff``; when a warehouse group exists, only this class changes.
    """

    message = "Only staff can adjust inventory."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for authenticated staff."""
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)

    def has_object_permission(
        self, request: Request, view: APIView, obj: models.Model
    ) -> bool:
        """Apply the same rule at object level."""
        return self.has_permission(request, view)
