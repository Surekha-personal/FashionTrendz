"""Cash on delivery.

A gateway with no gateway. It implements the interface so the payment flow has
exactly one shape whatever the method — the service layer never branches on
"is this COD" — but every operation is local: no network, no signature, no
webhook.

The money moves when the courier collects it, which the orders module already
handles by marking a delivered COD order paid.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.core.utils import generate_reference
from apps.payments.gateways.base import (
    BaseGateway,
    GatewayError,
    GatewayOrder,
    GatewayRefund,
    GatewayVerification,
    WebhookEvent,
)


class CashOnDeliveryGateway(BaseGateway):
    """Records the intent to pay in cash on delivery."""

    code = "cod"
    label = "Cash on delivery"
    is_offline = True

    def is_configured(self) -> bool:
        """Always configured — there is nothing to configure."""
        return True

    def create_order(
        self, *, amount: Decimal, currency: str, reference: str, notes: dict[str, Any]
    ) -> GatewayOrder:
        """Return a local reference. Nothing is sent anywhere.

        ``checkout_payload`` is empty on purpose: there is no widget to open,
        and the frontend uses its emptiness to know it should skip straight to
        the confirmation screen.
        """
        return GatewayOrder(
            gateway_order_id=generate_reference("COD", 12),
            amount=amount,
            currency=currency,
            checkout_payload={},
            raw={"method": "cod", "reference": reference},
        )

    def verify_payment(self, payload: dict[str, Any]) -> GatewayVerification:
        """Accept the intent without claiming the money has arrived.

        ``is_valid`` is true because the *order* is valid; the payment status
        stays pending until delivery. Returning false here would fail a
        perfectly good COD checkout.
        """
        return GatewayVerification(
            is_valid=True,
            gateway_order_id=str(payload.get("gateway_order_id", "")),
            method="cod",
            raw={"method": "cod", "captured": False},
        )

    def capture_payment(
        self, *, gateway_payment_id: str, amount: Decimal, currency: str
    ) -> dict[str, Any]:
        """Capture is a no-op; the courier does it."""
        return {"status": "pending", "method": "cod"}

    def refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        currency: str,
        notes: dict[str, Any],
    ) -> GatewayRefund:
        """Refuse. A COD refund is a bank transfer, not a gateway call.

        Failing loudly here is deliberate: silently returning "refunded" would
        close the ticket while the customer is still out of pocket.
        """
        raise GatewayError(
            "Cash-on-delivery orders are refunded by bank transfer, not through "
            "a payment gateway. Record the transfer manually."
        )

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """COD sends no webhooks."""
        raise GatewayError("Cash on delivery does not send webhooks.")

    def supports_refunds(self) -> bool:
        """COD refunds happen outside the platform."""
        return False
