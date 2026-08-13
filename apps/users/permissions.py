"""Object-level permissions for the users module."""

from __future__ import annotations

from typing import Any

from django.db import models
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsOwner(BasePermission):
    """Grant access only to the user who owns the object.

    ``AddressViewSet`` already narrows its queryset to the requesting user, so
    a foreign object 404s before it reaches here. This is the second layer: if
    a future view forgets to scope its queryset, the check still holds and the
    failure mode is 403 rather than a data leak.
    """

    message = "You do not have permission to access this resource."

    def has_object_permission(
        self,
        request: Request,
        view: APIView,
        obj: models.Model,
    ) -> bool:
        owner: Any = getattr(obj, "user", obj)
        return bool(request.user and request.user.is_authenticated and owner == request.user)
