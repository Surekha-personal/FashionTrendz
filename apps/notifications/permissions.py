"""Notification permissions.

Deliberately thin. Ownership is enforced by the queryset — every read and write
starts from ``Notification.objects.for_user(request.user)``, so there is no
path by which one customer addresses another's inbox and therefore no
object-level check to write.

What is left is the one rule the queryset cannot express.
"""

from __future__ import annotations

from typing import Any

from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.views import APIView


class CanManageNotificationQueue(permissions.BasePermission):
    """Staff who may drain or retry the delivery queue.

    Separate from plain staff read access because these two endpoints *send
    mail*. A misclick on "retry" against a large backlog is a customer-visible
    event, so the permission is named for what it allows rather than folded
    into a generic admin check.
    """

    message = "You do not have permission to manage the notification queue."

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Return whether the caller may operate the queue."""
        user: Any = request.user
        return bool(user and user.is_authenticated and user.is_staff)
