"""Structured logging helpers.

The one piece that matters here is the request-id context variable. Under any
concurrent server, log lines from different requests interleave, and a
traceback several lines below the request that caused it belongs to a different
customer as often as not. Stamping every record with the id of the request that
produced it makes a single request's lines greppable.

A :class:`contextvars.ContextVar` is used rather than thread-local storage
because it is correct under both threaded and async workers; thread-locals leak
between coroutines sharing a thread.

The module is named ``logging`` inside a package. Python 3 uses absolute
imports, so ``import logging`` below resolves to the standard library, not to
this file.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from apps.core.constants import REDACTED, SENSITIVE_KEYS
from apps.core.utils import client_ip, redact

#: Request id for the request currently being handled, or "-" outside one.
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def new_request_id() -> str:
    """Return a fresh short request identifier."""
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> Any:
    """Bind ``request_id`` to the current context and return the reset token."""
    return _request_id_var.set(request_id)


def get_request_id() -> str:
    """Return the request id bound to the current context."""
    return _request_id_var.get()


def reset_request_id(token: Any) -> None:
    """Unbind the request id using the token from :func:`set_request_id`."""
    try:
        _request_id_var.reset(token)
    except ValueError:
        # The token belongs to a different context — nothing to reset.
        pass


class RequestIDFilter(logging.Filter):
    """Attach ``request_id`` to every log record.

    A logging *filter* rather than a custom formatter, because a formatter that
    references ``%(request_id)s`` raises ``KeyError`` on any record that lacks
    the attribute — including records emitted by Django's own loggers during
    startup, before any request exists. Setting the attribute here guarantees
    it is always present.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Set ``record.request_id`` and always allow the record through."""
        record.request_id = get_request_id()
        return True


def get_logger(name: str) -> logging.Logger:
    """Return the project logger for ``name``.

    Thin wrapper over :func:`logging.getLogger`, kept so modules import from
    one place and the implementation can gain structured output later without
    touching every call site.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Convenience emitters
# ---------------------------------------------------------------------------

_api_logger = logging.getLogger("apps.api")
_error_logger = logging.getLogger("apps.error")


def log_request(request: Any, *, logger: logging.Logger | None = None) -> None:
    """Log an inbound API request with its body redacted.

    Body logging is opt-in per call rather than automatic, because request
    bodies contain card details and passwords. Everything routed through here
    passes :func:`apps.core.utils.redact` first.
    """
    target = logger or _api_logger
    body = redact(getattr(request, "data", {})) if hasattr(request, "data") else {}

    target.info(
        "request method=%s path=%s user=%s ip=%s body=%s",
        request.method,
        request.get_full_path(),
        getattr(getattr(request, "user", None), "pk", None) or "anonymous",
        client_ip(request),
        body,
    )


def log_response(
    request: Any,
    status_code: int,
    duration_ms: float,
    *,
    logger: logging.Logger | None = None,
) -> None:
    """Log a completed request with its status and duration.

    Level is chosen by status class so an error budget dashboard can count
    WARNING and ERROR lines without parsing the message.
    """
    target = logger or _api_logger

    if status_code >= 500:
        level = logging.ERROR
    elif status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO

    target.log(
        level,
        "response method=%s path=%s status=%s duration_ms=%.1f",
        request.method,
        request.get_full_path(),
        status_code,
        duration_ms,
    )


def log_exception(exc: BaseException, *, context: dict[str, Any] | None = None) -> None:
    """Log an exception with a full traceback and redacted context."""
    _error_logger.error(
        "exception type=%s message=%s context=%s",
        exc.__class__.__name__,
        exc,
        redact(context or {}),
        exc_info=exc,
    )


def safe_extra(**fields: Any) -> dict[str, Any]:
    """Build a redacted ``extra`` mapping for a logging call.

    Guards against a caller passing a token or password straight into
    structured log fields::

        logger.info("checkout", extra=safe_extra(order_id=o.pk, token=t))
    """
    return {
        key: REDACTED if key.lower() in SENSITIVE_KEYS else value
        for key, value in fields.items()
    }


class Timer:
    """Context manager measuring a block's wall time in milliseconds.

    Uses :func:`time.perf_counter`, which is monotonic. ``time.time`` can jump
    backwards when NTP corrects the clock, producing negative durations in the
    logs::

        with Timer() as t:
            gateway.charge(order)
        logger.info("charge took %.1fms", t.elapsed_ms)
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: float = 0.0

    def __enter__(self) -> "Timer":
        """Start the timer."""
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        """Stop the timer and record the elapsed milliseconds."""
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000
