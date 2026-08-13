"""Review permissions."""

from __future__ import annotations

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.reviews.models import Review


class IsReviewAuthor(permissions.BasePermission):
    """Only the author may edit or delete their review.

    Object-level rather than filtering the queryset, so an attempt on someone
    else's review returns 403 and not a silent 404 — the author of a genuine
    mis-typed id gets a message that explains itself.
    """

    message = "You can only modify your own review."

    def has_object_permission(
        self, request: Request, view: APIView, obj: Review
    ) -> bool:
        """Return whether the caller wrote this review."""
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user
            and request.user.is_authenticated
            and obj.user_id == request.user.pk
        )


class IsReviewModerator(permissions.BasePermission):
    """Staff who may approve or reject reviews.

    Staff rather than a dedicated group: this store has one admin surface, and
    a permission group with one member is a table nobody maintains.
    """

    message = "You do not have permission to moderate reviews."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return whether the caller is staff."""
        user: Any = request.user
        return bool(user and user.is_authenticated and user.is_staff)
