"""Custom exceptions and the global DRF exception handler.

Installed as ``REST_FRAMEWORK["EXCEPTION_HANDLER"]``, so every failure — a
serializer rejection, a missing object, an expired token, a database constraint
violation or an outright bug — leaves the process in the same JSON shape.

The handler writes the *complete* envelope into ``response.data`` rather than
letting the renderer do it. Errors are what tests and log readers inspect most,
and having the final shape available before rendering makes both easier.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("apps.core.exceptions")

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class BusinessRuleViolation(APIException):
    """A request was well-formed but not allowed by a domain rule.

    Use where the input is valid in isolation but the action is not permitted
    right now — cancelling a delivered order, applying an expired coupon,
    checking out an empty cart. Distinct from a serializer ``ValidationError``,
    which means "this field is wrong".
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This action is not allowed in the current state."
    default_code = "business_rule_violation"


class ResourceConflict(APIException):
    """The request conflicts with the current state of the resource.

    The correct status for "someone already took that slug" or "this order was
    already paid" — 409 tells the client to re-read and retry, which 400 does not.
    """

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This request conflicts with the current state of the resource."
    default_code = "resource_conflict"


class InsufficientStock(APIException):
    """A cart or order line asked for more units than are available."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "There is not enough stock to fulfil this request."
    default_code = "insufficient_stock"


class ServiceUnavailable(APIException):
    """A dependency this request needs — payment gateway, SMS provider — is down."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "This service is temporarily unavailable. Please try again shortly."
    default_code = "service_unavailable"


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _stringify(detail: Any) -> Any:
    """Convert DRF ``ErrorDetail`` objects into plain JSON types, recursively."""
    if isinstance(detail, dict):
        return {key: _stringify(value) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_stringify(item) for item in detail]
    return str(detail)


def _normalise_errors(detail: Any) -> dict[str, Any]:
    """Coerce any DRF error detail into a ``{field: [messages]}`` mapping.

    DRF hands back three different shapes depending on how the error was
    raised: a dict for field errors, a list for ``non_field_errors``, and a
    bare string for most non-validation exceptions. Clients should not have to
    branch on all three, so everything becomes a dict here.
    """
    normalised = _stringify(detail)

    if isinstance(normalised, dict):
        return {
            key: value if isinstance(value, list) else [value]
            for key, value in normalised.items()
        }
    if isinstance(normalised, list):
        return {"non_field_errors": normalised}
    return {"detail": [normalised]}


def _summarise(errors: dict[str, Any], fallback: str) -> str:
    """Pick a single human-readable message from a field-error mapping."""
    if set(errors.keys()) == {"detail"} and errors["detail"]:
        return str(errors["detail"][0])
    if errors:
        return "Validation failed. Please check the highlighted fields."
    return fallback


def _envelope(message: str, errors: dict[str, Any], status_code: int) -> Response:
    """Build the standard failure response."""
    return Response(
        {"success": False, "message": message, "errors": errors},
        status=status_code,
    )


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return a uniform error response for any exception raised inside a view.

    Order of handling:

    1. DRF's own handler covers ``APIException`` and its subclasses, plus
       ``Http404`` and Django's ``PermissionDenied``, which it converts for us.
       Its output is reshaped into the envelope.
    2. Django's ``ValidationError`` — raised by ``full_clean()`` and by model
       field validators — is translated to a 400 rather than escaping as a 500.
    3. ``IntegrityError`` becomes 409, not 500: a unique or check constraint
       firing means the *request* conflicts with stored state, which is a
       client-correctable condition.
    4. Anything else is a bug. It is logged with a full traceback and answered
       with a generic 500 that leaks nothing about the internals.
    """
    response = drf_exception_handler(exc, context)
    view = context.get("view")
    request = context.get("request")
    view_name = view.__class__.__name__ if view else "unknown"

    if response is not None:
        errors = _normalise_errors(response.data)

        if isinstance(exc, ValidationError):
            message = _summarise(errors, "Validation failed.")
        else:
            message = _summarise(errors, str(getattr(exc, "detail", exc)))

        # 5xx from a DRF exception is still a server-side problem worth a trace.
        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            logger.error("%s raised %s", view_name, exc.__class__.__name__, exc_info=exc)

        return _envelope(message, errors, response.status_code)

    if isinstance(exc, Http404):
        return _envelope(
            "The requested resource was not found.",
            {"detail": ["Not found."]},
            status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return _envelope(
            "You do not have permission to perform this action.",
            {"detail": ["Permission denied."]},
            status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, DjangoValidationError):
        errors = _normalise_errors(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )
        return _envelope(
            _summarise(errors, "Validation failed."),
            errors,
            status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, IntegrityError):
        # The driver's message quotes constraint names, table names and often
        # the offending value. None of that goes to the client.
        logger.warning("IntegrityError in %s: %s", view_name, exc)
        return _envelope(
            "This request conflicts with existing data.",
            {"detail": ["A record with these details already exists, "
                        "or a related record is missing."]},
            status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DatabaseError):
        logger.error("DatabaseError in %s", view_name, exc_info=exc)
        return _envelope(
            "A database error occurred. Please try again.",
            {"detail": ["Database unavailable."]},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.exception(
        "Unhandled %s in %s (%s %s)",
        exc.__class__.__name__,
        view_name,
        getattr(request, "method", "?"),
        getattr(request, "path", "?"),
    )
    return _envelope(
        "An unexpected error occurred. The issue has been logged.",
        {"detail": ["Internal server error."]},
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
