"""Razorpay gateway — the fully implemented one.

No SDK. The two security-critical operations are plain HMAC-SHA256, which must
be done here whatever library is installed, and the three API calls are simple
authenticated POSTs. Adding a dependency to save six lines of ``urllib`` is not
a trade worth making, and it keeps the deployment free of a transitive
``requests`` chain.

Swapping in ``requests`` or ``httpx`` later means replacing :meth:`_request`
and nothing else.

Reference: https://razorpay.com/docs/api/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from django.conf import settings

from apps.core.logging import get_logger
from apps.payments.gateways.base import (
    BaseGateway,
    GatewayError,
    GatewayOrder,
    GatewayRefund,
    GatewayVerification,
    SignatureError,
    WebhookEvent,
)

logger = get_logger(__name__)

API_ROOT = "https://api.razorpay.com/v1"
REQUEST_TIMEOUT = 20

#: Razorpay webhook events this integration understands. Anything else is
#: logged and acknowledged — returning an error for an event we simply do not
#: handle makes the provider retry it forever.
HANDLED_EVENTS: frozenset[str] = frozenset(
    {
        "payment.captured",
        "payment.authorized",
        "payment.failed",
        "order.paid",
        "refund.created",
        "refund.processed",
        "refund.failed",
    }
)


def to_paise(amount: Decimal) -> int:
    """Convert rupees to the integer paise Razorpay expects.

    Integer arithmetic on a quantised Decimal, never a float: ``int(19.99 *
    100)`` is 1998 in floating point, and that missing paise is a reconciliation
    failure nobody can explain a month later.
    """
    return int((Decimal(str(amount)).quantize(Decimal("0.01")) * 100).to_integral_value())


def from_paise(paise: int | str | None) -> Decimal:
    """Convert integer paise back to rupees."""
    return (Decimal(str(paise or 0)) / Decimal("100")).quantize(Decimal("0.01"))


class RazorpayGateway(BaseGateway):
    """Razorpay Standard Checkout integration."""

    code = "razorpay"
    label = "Razorpay"
    is_offline = False

    # -- Configuration ------------------------------------------------------

    @property
    def key_id(self) -> str:
        """Return the publishable key id."""
        return getattr(settings, "RAZORPAY_KEY_ID", "") or ""

    @property
    def key_secret(self) -> str:
        """Return the secret key used for API auth and payment signatures."""
        return getattr(settings, "RAZORPAY_KEY_SECRET", "") or ""

    @property
    def webhook_secret(self) -> str:
        """Return the webhook signing secret.

        A *separate* secret from the API key, set independently in the Razorpay
        dashboard. Using the API secret to verify webhooks is a common and
        silent misconfiguration — every webhook simply fails to verify.
        """
        return getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or ""

    def is_configured(self) -> bool:
        """Return whether both API credentials are present."""
        return bool(self.key_id and self.key_secret)

    def _assert_configured(self) -> None:
        """Raise unless credentials are present."""
        if not self.is_configured():
            raise GatewayError(
                "Razorpay is not configured. Set RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET."
            )

    # -- Transport ----------------------------------------------------------

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make one authenticated call to the Razorpay API.

        The only place in this module that touches the network. Every failure
        mode — HTTP error, timeout, unparseable body — becomes a
        :class:`GatewayError`, so callers never see a ``URLError``.
        """
        self._assert_configured()

        url = f"{API_ROOT}{path}"
        body = json.dumps(payload).encode() if payload is not None else None
        credentials = base64.b64encode(
            f"{self.key_id}:{self.key_secret}".encode()
        ).decode()

        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Authorization", f"Basic {credentials}")
        request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            detail = self._error_detail(exc)
            logger.error("razorpay %s %s failed: %s", method, path, detail)
            raise GatewayError(f"Razorpay rejected the request: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.error("razorpay %s %s unreachable: %s", method, path, exc)
            raise GatewayError("Could not reach Razorpay. Please try again.") from exc
        except json.JSONDecodeError as exc:
            logger.error("razorpay %s %s returned unparseable JSON", method, path)
            raise GatewayError("Razorpay returned an unexpected response.") from exc

    @staticmethod
    def _error_detail(exc: urllib.error.HTTPError) -> str:
        """Extract Razorpay's error description, without leaking the raw body."""
        try:
            payload = json.loads(exc.read().decode() or "{}")
            return str(payload.get("error", {}).get("description", exc.reason))
        except Exception:  # pragma: no cover - defensive
            return str(exc.reason)

    # -- Operations ---------------------------------------------------------

    def create_order(
        self, *, amount: Decimal, currency: str, reference: str, notes: dict[str, Any]
    ) -> GatewayOrder:
        """Create a Razorpay order and return the browser checkout payload.

        ``receipt`` carries our order number, which is what makes the two
        systems reconcilable from either side during a dispute.
        """
        response = self._request(
            "POST",
            "/orders",
            {
                "amount": to_paise(amount),
                "currency": currency,
                "receipt": reference[:40],
                "notes": {k: str(v)[:255] for k, v in notes.items()},
                # Auto-capture. Manual capture means a two-step flow where an
                # authorised-but-uncaptured payment expires silently after a
                # few days, and the customer is left believing they paid.
                "payment_capture": 1,
            },
        )

        return GatewayOrder(
            gateway_order_id=response["id"],
            amount=from_paise(response.get("amount")),
            currency=response.get("currency", currency),
            checkout_payload={
                "key": self.key_id,
                "order_id": response["id"],
                "amount": response.get("amount"),
                "currency": response.get("currency", currency),
                "name": "Fashion Trendz",
                "description": reference,
                "notes": response.get("notes", {}),
            },
            raw=response,
        )

    def verify_payment(self, payload: dict[str, Any]) -> GatewayVerification:
        """Verify the signature the browser returns after checkout.

        Razorpay signs ``"{order_id}|{payment_id}"`` with the **API secret**.
        This is the one check standing between a real payment and a forged
        callback, so it uses ``hmac.compare_digest`` — a plain ``==`` on a
        signature leaks its correctness one byte at a time through timing.
        """
        self._assert_configured()

        order_id = payload.get("razorpay_order_id", "")
        payment_id = payload.get("razorpay_payment_id", "")
        signature = payload.get("razorpay_signature", "")

        if not (order_id and payment_id and signature):
            return GatewayVerification(
                is_valid=False, failure_reason="Incomplete payment response."
            )

        expected = hmac.new(
            self.key_secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning(
                "razorpay signature mismatch order=%s payment=%s", order_id, payment_id
            )
            return GatewayVerification(
                is_valid=False,
                gateway_order_id=order_id,
                gateway_payment_id=payment_id,
                failure_reason="Signature verification failed.",
            )

        # Signature proves the message came from Razorpay. Fetching the payment
        # proves it is actually captured and for the amount we expect — a valid
        # signature on a *failed* payment is still a valid signature.
        details = self._request("GET", f"/payments/{payment_id}")

        return GatewayVerification(
            is_valid=details.get("status") in {"captured", "authorized"},
            gateway_payment_id=payment_id,
            gateway_order_id=order_id,
            signature=signature,
            amount=from_paise(details.get("amount")),
            method=str(details.get("method", "")),
            raw=details,
            failure_reason=""
            if details.get("status") in {"captured", "authorized"}
            else f"Payment status is {details.get('status')}.",
        )

    def capture_payment(
        self, *, gateway_payment_id: str, amount: Decimal, currency: str
    ) -> dict[str, Any]:
        """Capture an authorised payment.

        Rarely needed — ``payment_capture: 1`` on the order makes Razorpay
        capture automatically. Kept for the manual-capture flow and for
        recovering a payment left authorised by a failed callback.
        """
        return self._request(
            "POST",
            f"/payments/{gateway_payment_id}/capture",
            {"amount": to_paise(amount), "currency": currency},
        )

    def refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        currency: str,
        notes: dict[str, Any],
    ) -> GatewayRefund:
        """Refund all or part of a captured payment.

        ``speed: normal`` rather than ``optimum``: instant refunds cost extra
        and the difference is invisible to the customer, who sees "refund
        initiated" either way.
        """
        response = self._request(
            "POST",
            f"/payments/{gateway_payment_id}/refund",
            {
                "amount": to_paise(amount),
                "speed": "normal",
                "notes": {k: str(v)[:255] for k, v in notes.items()},
            },
        )

        return GatewayRefund(
            refund_id=response["id"],
            amount=from_paise(response.get("amount")),
            status=str(response.get("status", "pending")),
            raw=response,
        )

    # -- Webhooks -----------------------------------------------------------

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Verify and normalise a Razorpay webhook.

        The signature is HMAC-SHA256 of the **raw request body** with the
        webhook secret. Raw matters: re-serialising the parsed JSON reorders
        keys and changes whitespace, and the signature then never matches —
        which is why the view hands ``request.body`` through untouched.
        """
        if not self.webhook_secret:
            raise GatewayError(
                "Razorpay webhooks are not configured. Set RAZORPAY_WEBHOOK_SECRET."
            )

        signature = headers.get("X-Razorpay-Signature", "") or headers.get(
            "HTTP_X_RAZORPAY_SIGNATURE", ""
        )
        if not signature:
            raise SignatureError("Missing webhook signature.")

        expected = hmac.new(
            self.webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning("razorpay webhook signature mismatch")
            raise SignatureError("Webhook signature verification failed.")

        try:
            payload = json.loads(body.decode() or "{}")
        except json.JSONDecodeError as exc:
            raise SignatureError("Webhook body is not valid JSON.") from exc

        return self._normalise_event(payload)

    def _normalise_event(self, payload: dict[str, Any]) -> WebhookEvent:
        """Flatten Razorpay's nested envelope into a :class:`WebhookEvent`."""
        event_type = str(payload.get("event", ""))
        entities = payload.get("payload", {})

        payment = entities.get("payment", {}).get("entity", {}) or {}
        refund = entities.get("refund", {}).get("entity", {}) or {}
        order = entities.get("order", {}).get("entity", {}) or {}

        entity = refund or payment or order
        amount = from_paise(entity.get("amount")) if entity else None

        # Razorpay does not send a dedicated event id in the body, so the id is
        # derived from the entity — which is stable across the provider's
        # retries of the same event, and that is exactly what idempotency needs.
        event_id = f"{event_type}:{entity.get('id', '')}"

        return WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            gateway_payment_id=str(payment.get("id", "") or refund.get("payment_id", "")),
            gateway_order_id=str(payment.get("order_id", "") or order.get("id", "")),
            gateway_refund_id=str(refund.get("id", "")),
            amount=amount,
            status=str(entity.get("status", "")),
            failure_reason=str(
                payment.get("error_description", "") or payment.get("error_reason", "")
            ),
            raw=payload,
        )
