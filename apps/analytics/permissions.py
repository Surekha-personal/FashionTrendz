"""Analytics permissions."""

from __future__ import annotations

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class IsAnalyticsViewer(permissions.BasePermission):
    """Staff who may read business figures.

    Every endpoint in this app returns revenue, customer emails or both. That
    is the most sensitive data the API serves — more so than any single order,
    because it is all of them at once — so the check is explicit here rather
    than inherited from a generic admin permission that might loosen later.
    """

    message = "You do not have permission to view analytics."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return whether the caller is staff.

        Read-only endpoints still require staff. "It is only a GET" is how
        revenue ends up in a screenshot.
        """
        user: Any = request.user
        return bool(user and user.is_authenticated and user.is_staff)
