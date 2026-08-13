"""Reusable permission classes.

The project default is ``IsAuthenticated`` (set in Module 1), so these classes
narrow or widen from a closed baseline. A view that forgets to set
``permission_classes`` stays private.
"""

from __future__ import annotations

from typing import Any

from django.db import models
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


def _is_authenticated(request: Request) -> bool:
    """Return whether the request carries a usable authenticated user."""
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated)


class IsAdmin(BasePermission):
    """Allow only staff accounts.

    Checks ``is_staff`` rather than ``is_superuser``: superuser is an escape
    hatch for one or two accounts, while staff is the flag that scales to a
    real operations team.
    """

    message = "Administrator access is required for this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for authenticated staff."""
        return _is_authenticated(request) and request.user.is_staff


class IsCustomer(BasePermission):
    """Allow only authenticated non-staff accounts.

    Used for endpoints that only make sense for a shopper — cart, wishlist,
    "my orders". Excluding staff is intentional: a staff account has no cart,
    and letting one silently create shopper-scoped rows makes support data
    confusing later.
    """

    message = "This action is only available to customer accounts."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for authenticated users who are not staff."""
        return _is_authenticated(request) and not request.user.is_staff


class ReadOnly(BasePermission):
    """Allow ``GET``, ``HEAD`` and ``OPTIONS`` only, for anyone.

    Combine with another class rather than using it alone::

        permission_classes = [IsAdmin | ReadOnly]
    """

    message = "This resource is read-only."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for safe HTTP methods."""
        return request.method in SAFE_METHODS


class AdminOrReadOnly(BasePermission):
    """Public reads, staff-only writes.

    The permission for catalogue data: anyone may browse products and
    categories, only staff may change them.
    """

    message = "Only administrators can modify this resource."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for safe methods, or for authenticated staff."""
        if request.method in SAFE_METHODS:
            return True
        return _is_authenticated(request) and request.user.is_staff


class OwnerOnly(BasePermission):
    """Allow access only to the user who owns the object.

    Reads the owner from ``obj.<owner_field>``, defaulting to ``user``. A view
    may point it elsewhere::

        class ReviewViewSet(ModelViewSet):
            permission_classes = [IsAuthenticated, OwnerOnly]
            owner_field = "author"

    This is a second line of defence, not the first. Views should still scope
    ``get_queryset()`` to the requesting user so a foreign object returns 404
    rather than 403 — a 403 confirms the object exists, which is itself a leak.
    """

    message = "You do not have permission to access this resource."
    default_owner_field = "user"

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: models.Model,
    ) -> bool:
        """Return True when the requesting user owns ``obj``."""
        if not _is_authenticated(request):
            return False

        owner_field = getattr(view, "owner_field", self.default_owner_field)
        owner: Any = getattr(obj, owner_field, obj)
        return owner == request.user


class OwnerOrAdmin(OwnerOnly):
    """Allow the owner, or any staff account.

    For resources a customer manages but support staff must also inspect —
    orders, returns, support tickets.
    """

    message = "You do not have permission to access this resource."

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: models.Model,
    ) -> bool:
        """Return True for staff, or when the requesting user owns ``obj``."""
        if _is_authenticated(request) and request.user.is_staff:
            return True
        return super().has_object_permission(request, view, obj)


class IsAuthenticatedOrReadOnly(BasePermission):
    """Public reads, authenticated writes.

    Named to match DRF's own class but re-declared here so views can import
    every permission they need from one module.
    """

    message = "You must be signed in to modify this resource."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return True for safe methods, or for any authenticated user."""
        return request.method in SAFE_METHODS or _is_authenticated(request)
