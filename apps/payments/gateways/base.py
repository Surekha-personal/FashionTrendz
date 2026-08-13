"""The gateway abstraction.

Every provider implements the same six operations against the same four
dataclasses. Nothing above this layer knows what Razorpay's JSON looks like,
which is what makes adding Stripe a new file rather than a refactor.

Amounts cross this boundary as :class:`~decimal.Decimal` rupees. Conversion to
a gateway's own unit — Razorpay and Stripe both want integer paise/cents — is
each gateway's job. Doing it once per gateway, at the edge, is what keeps
float rounding out of the money path entirely.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.core.exceptions import ServiceUnavailable


class GatewayError(ServiceUnavailable):
    """A gateway call failed.

    Subclasses ``ServiceUnavailable`` so an unreachable provider surfaces as a
    503 the client can retry, rather than a 500 that reads as our bug.
    """

    default_detail = "The payment provider is unavailable. Please try again."


class SignatureError(GatewayError):
    """A signature did not verify.

    A separate exception because the response differs: a bad signature is
    never retried, and it is always logged as a security event.
    """

    status_code = 400
    default_detail = "Payment verification failed."


@dataclass(frozen=True)
class GatewayOrder:
    """A payment intent created at the provider."""

    gateway_order_id: str
    amount: Decimal
    currency: str
    #: Everything the browser SDK needs to open the checkout widget.
    checkout_payload: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayVerification:
    """The outcome of verifying a completed payment."""

    is_valid: bool
    gateway_payment_id: str = ""
    gateway_order_id: str = ""
    signature: str = ""
    amount: Decimal | None = None
    method: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    failure_reason: str = ""


@dataclass(frozen=True)
class GatewayRefund:
    """A refund created at the provider."""

    refund_id: str
    amount: Decimal
    status: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WebhookEvent:
    """A verified, normalised webhook.

    ``event_id`` is what makes processing idempotent — it is the unique key the
    webhook log stores, so a provider retrying the same event five times writes
    one row and processes once.
    """

    event_id: str
    event_type: str
    gateway_payment_id: str = ""
    gateway_order_id: str = ""
    gateway_refund_id: str = ""
    amount: Decimal | None = None
    status: str = ""
    failure_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class BaseGateway(ABC):
    """What every payment provider must implement."""

    #: Registry key, matching ``Payment.gateway``.
    code: str = ""

    #: Human label for the checkout page.
    label: str = ""

    #: Whether this provider settles without a browser round-trip.
    is_offline: bool = False

    @abstractmethod
    def is_configured(self) -> bool:
        """Return whether credentials are present.

        Checked before every call so a missing key fails at the API boundary
        with a clear message, rather than as an auth error from the provider
        three layers down.
        """

    @abstractmethod
    def create_order(
        self, *, amount: Decimal, currency: str, reference: str, notes: dict[str, Any]
    ) -> GatewayOrder:
        """Create a payment intent and return what the client needs to pay."""

    @abstractmethod
    def verify_payment(self, payload: dict[str, Any]) -> GatewayVerification:
        """Verify a completed payment reported by the client.

        **Never trust the client.** The browser tells us a payment succeeded;
        this method proves it, either by signature or by asking the provider.
        """

    @abstractmethod
    def capture_payment(
        self, *, gateway_payment_id: str, amount: Decimal, currency: str
    ) -> dict[str, Any]:
        """Capture an authorised payment."""

    @abstractmethod
    def refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        currency: str,
        notes: dict[str, Any],
    ) -> GatewayRefund:
        """Refund all or part of a captured payment."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify a webhook's signature and normalise its body.

        Raises :class:`SignatureError` when the signature does not match. An
        unverified webhook is an unauthenticated stranger telling the store an
        order was paid for.
        """

    def supports_refunds(self) -> bool:
        """Return whether refunds can be issued through this provider."""
        return True

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} code={self.code}>"
