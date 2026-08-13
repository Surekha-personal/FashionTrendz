"""Recommendation permissions."""

from __future__ import annotations

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsRecommendationAdmin(permissions.BasePermission):
    """Staff who may read the trending dashboard and diagnostics.

    Both surfaces expose the ranking formula's inputs and weights. That is
    merchandising intelligence — and, in the diagnostics case, aggregate
    browsing behaviour — neither of which belongs on a public endpoint.
    """

    message = "You do not have permission to view recommendation diagnostics."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return whether the caller is staff."""
        user: Any = request.user
        return bool(user and user.is_authenticated and user.is_staff)
