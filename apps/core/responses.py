"""The standard API response envelope.

Every response this backend emits has the same top-level shape:

Success::

    {"success": true, "message": "...", "data": {...}}

Failure::

    {"success": false, "message": "...", "errors": {...}}

The envelope is applied by :class:`EnvelopeJSONRenderer`, which is installed
globally as the default renderer. Views therefore need no special base class
and no per-view wrapping — a stock ``ModelViewSet`` produces enveloped output
automatically, and the Module 2 endpoints written before this module existed
conform without being edited.

Two consequences worth knowing when writing tests:

* ``response.data`` holds the *unenveloped* payload for success responses,
  because rendering happens after the view returns. Assert on ``response.data``
  for the payload and ``response.json()`` for the wire format.
* Error responses are the exception: :mod:`apps.core.exceptions` builds the
  full envelope as ``response.data`` so failures are inspectable without
  rendering. The renderer detects the ``success`` key and passes them through.
"""

from __future__ import annotations

from typing import Any, Mapping

from rest_framework import status as http_status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

#: Fallback success text, chosen by request method when a view supplies none.
DEFAULT_SUCCESS_MESSAGES: dict[str, str] = {
    "GET": "Request successful.",
    "POST": "Created successfully.",
    "PUT": "Updated successfully.",
    "PATCH": "Updated successfully.",
    "DELETE": "Deleted successfully.",
}

DEFAULT_ERROR_MESSAGE: str = "Request failed."


def success_response(
    data: Any = None,
    message: str = "Request successful.",
    status: int = http_status.HTTP_200_OK,
    **kwargs: Any,
) -> Response:
    """Return a success ``Response`` carrying an explicit message.

    Only needed when the default method-derived message is not descriptive
    enough — for example "Coupon applied." rather than "Updated successfully.".
    The envelope itself is added by the renderer either way.
    """
    response = Response(data if data is not None else {}, status=status, **kwargs)
    response.message = message
    return response


def error_response(
    message: str = DEFAULT_ERROR_MESSAGE,
    errors: Mapping[str, Any] | None = None,
    status: int = http_status.HTTP_400_BAD_REQUEST,
    **kwargs: Any,
) -> Response:
    """Return a failure ``Response`` in the standard error shape.

    Prefer raising a DRF exception where one fits — the global handler formats
    it identically and keeps the failure path in one place. This helper is for
    the cases where a view must fail without an exception being the natural
    control flow.
    """
    return Response(
        {"success": False, "message": message, "errors": dict(errors or {})},
        status=status,
        **kwargs,
    )


def build_envelope(
    data: Any,
    *,
    message: str,
    success: bool = True,
) -> dict[str, Any]:
    """Assemble an envelope dict from an already-serialised payload."""
    key = "data" if success else "errors"
    return {"success": success, "message": message, key: data}


class EnvelopeJSONRenderer(JSONRenderer):
    """Wrap every JSON payload in the standard envelope.

    Installed as the default renderer, so it runs for every view including
    third-party ones such as SimpleJWT's token endpoints.

    Payloads it recognises and treats specially:

    * anything already containing a ``success`` key — passed through untouched,
      which is how error envelopes and pre-built responses survive;
    * ``{"pagination": ..., "results": ...}`` from the core paginators — the
      results become ``data`` and pagination is hoisted to the top level, so a
      list response is a JSON array rather than an object wrapping one;
    * ``{"detail": "..."}`` — DRF's single-message shape, which becomes the
      envelope's ``message`` instead of being buried one level down.
    """

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: Mapping[str, Any] | None = None,
    ) -> bytes:
        """Envelope ``data`` and delegate the actual encoding to DRF."""
        context = renderer_context or {}
        response = context.get("response")
        request = context.get("request")

        payload = self._envelope(data, response, request)
        return super().render(payload, accepted_media_type, renderer_context)

    def _envelope(self, data: Any, response: Any, request: Any) -> Any:
        """Return the enveloped form of ``data``."""
        # An empty 204 body must stay empty; a JSON object would violate the
        # HTTP semantics of "no content" and breaks some strict clients.
        if data is None:
            return None

        if isinstance(data, dict) and "success" in data:
            return data

        status_code = getattr(response, "status_code", http_status.HTTP_200_OK)
        succeeded = status_code < http_status.HTTP_400_BAD_REQUEST
        message = getattr(response, "message", None)

        if not succeeded:
            # A view returned a raw error body without going through the
            # exception handler. Normalise it rather than leaking the shape.
            detail, errors = self._split_detail(data)
            return {
                "success": False,
                "message": message or detail or DEFAULT_ERROR_MESSAGE,
                "errors": errors,
            }

        if isinstance(data, dict) and set(data.keys()) == {"pagination", "results"}:
            return {
                "success": True,
                "message": message or self._default_message(request, status_code),
                "data": data["results"],
                "pagination": data["pagination"],
            }

        if isinstance(data, dict) and set(data.keys()) == {"detail"}:
            return {
                "success": True,
                "message": message or str(data["detail"]),
                "data": {},
            }

        return {
            "success": True,
            "message": message or self._default_message(request, status_code),
            "data": data,
        }

    @staticmethod
    def _split_detail(data: Any) -> tuple[str | None, dict[str, Any]]:
        """Separate a human message from field errors in a raw error body."""
        if isinstance(data, dict):
            if set(data.keys()) == {"detail"}:
                return str(data["detail"]), {}
            return None, dict(data)
        if isinstance(data, list):
            return None, {"non_field_errors": data}
        return str(data), {}

    @staticmethod
    def _default_message(request: Any, status_code: int) -> str:
        """Derive a message from the request method when the view supplied none."""
        if status_code == http_status.HTTP_201_CREATED:
            return DEFAULT_SUCCESS_MESSAGES["POST"]
        method = getattr(request, "method", "GET")
        return DEFAULT_SUCCESS_MESSAGES.get(method, "Request successful.")
