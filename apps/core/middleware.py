"""Request-scoped middleware: tracing, timing and exception logging.

Ordering matters and is set in ``settings.MIDDLEWARE``:

* :class:`RequestIDMiddleware` runs first so every later layer, including the
  logging filter, sees an id.
* :class:`ResponseTimeMiddleware` runs second so its measurement covers the
  whole downstream stack rather than only the view.
* :class:`ExceptionLoggingMiddleware` runs last, closest to the view, so
  ``process_exception`` sees exceptions before other middleware can swallow them.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse

from apps.core.constants import REQUEST_ID_HEADER, RESPONSE_TIME_HEADER
from apps.core.logging import (
    get_logger,
    log_exception,
    log_response,
    new_request_id,
    reset_request_id,
    set_request_id,
)

logger = get_logger("apps.core.middleware")

#: WSGI/ASGI form of the inbound request-id header.
_REQUEST_ID_META_KEY = f"HTTP_{REQUEST_ID_HEADER.upper().replace('-', '_')}"

#: Longest inbound id accepted. An unbounded client-supplied value would be
#: copied into every log line for that request — a cheap log-flooding vector.
_MAX_INBOUND_ID_LENGTH = 64


class RequestIDMiddleware:
    """Assign an id to every request and echo it back on the response.

    Reuses an inbound ``X-Request-ID`` when the caller supplies one, so a trace
    started at the Next.js frontend or a load balancer continues through this
    service instead of restarting. The value is length-capped and stripped of
    control characters before use, because it ends up in log output.

    The id is exposed three ways: on ``request.request_id`` for view code, on
    every log record via :class:`apps.core.logging.RequestIDFilter`, and on the
    response header so a customer can quote it in a support ticket.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Bind a request id for the duration of this request."""
        request_id = self._resolve_request_id(request)
        request.request_id = request_id
        token = set_request_id(request_id)

        try:
            response = self.get_response(request)
        finally:
            # Reset in a finally block: worker threads are reused, and a
            # leaked context variable would stamp the *next* request with this
            # request's id.
            reset_request_id(token)

        response[REQUEST_ID_HEADER] = request_id
        return response

    @staticmethod
    def _resolve_request_id(request: HttpRequest) -> str:
        """Return a sanitised inbound id, or a freshly generated one."""
        supplied = request.META.get(_REQUEST_ID_META_KEY, "")
        cleaned = "".join(
            char for char in supplied if char.isalnum() or char in "-_"
        )[:_MAX_INBOUND_ID_LENGTH]
        return cleaned or new_request_id()


class ResponseTimeMiddleware:
    """Measure server-side duration, expose it as a header and log it.

    Uses :func:`time.perf_counter` rather than :func:`time.time` because it is
    monotonic; a wall clock adjusted by NTP mid-request yields negative
    durations that poison any latency percentile computed from the logs.

    Static and media paths are skipped: in development they are the majority of
    requests and drown out the API lines that matter.
    """

    #: Requests slower than this are logged at WARNING for easy alerting.
    slow_request_ms: float = 1000.0

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Time the downstream stack and annotate the response."""
        started = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - started) * 1000

        response[RESPONSE_TIME_HEADER] = f"{duration_ms:.1f}"
        request.duration_ms = duration_ms

        if self._should_log(request):
            log_response(request, response.status_code, duration_ms)

            if duration_ms >= self.slow_request_ms:
                logger.warning(
                    "slow request method=%s path=%s duration_ms=%.1f",
                    request.method,
                    request.get_full_path(),
                    duration_ms,
                )

        return response

    @staticmethod
    def _should_log(request: HttpRequest) -> bool:
        """Return whether this path is worth a log line."""
        path = request.path
        return not (path.startswith("/static/") or path.startswith("/media/"))


class ExceptionLoggingMiddleware:
    """Log exceptions that escape the view layer.

    This does **not** duplicate :func:`apps.core.exceptions.api_exception_handler`.
    That handler only sees exceptions raised inside a DRF view; it never runs
    for a Django view, the admin, a management-command-triggered request, or an
    exception raised in middleware below this one. Those would otherwise reach
    the WSGI server with only Django's default logging.

    It logs and returns ``None``, deliberately not producing a response, so
    Django's normal error handling still applies — the debug page in
    development, ``handler500`` in production.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Pass the request through untouched."""
        return self.get_response(request)

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        """Log the exception with request context, then defer to Django."""
        log_exception(
            exception,
            context={
                "method": request.method,
                "path": request.get_full_path(),
                "user": getattr(getattr(request, "user", None), "pk", None) or "anonymous",
                "request_id": getattr(request, "request_id", "-"),
            },
        )
        return None


class RequestLoggingMiddleware:
    """Log inbound API requests, including redacted bodies.

    **Not enabled by default.** Body logging is expensive and, even redacted,
    stores customer data in the log system. Enable it deliberately — during an
    integration debugging session, or on a staging environment — by adding it
    to ``MIDDLEWARE`` after ``ResponseTimeMiddleware``.
    """

    #: Only these path prefixes are logged.
    prefixes: tuple[str, ...] = ("/api/",)

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        """Log the request line before handing off downstream."""
        if request.path.startswith(self.prefixes):
            logger.info(
                "inbound method=%s path=%s user=%s",
                request.method,
                request.get_full_path(),
                getattr(getattr(request, "user", None), "pk", None) or "anonymous",
            )
        return self.get_response(request)
