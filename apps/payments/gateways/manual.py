"""Placeholder gateway for providers that are not integrated yet.

Stripe, PayU and Cashfree resolve here. It implements the interface so the
checkout page can list them and the payment records have somewhere to point,
but it **never claims a payment succeeded**.

That refusal is the whole design. A stub that returns "captured" is how a store
ships orders nobody paid for — the tests pass, the demo works, and the loss
only surfaces at the end of the month. This one creates the record, leaves the
payment pending, and says clearly that a human has to confirm the money.
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


class ManualGateway(BaseGateway):
    """Records a payment intent without contacting any provider."""

    code = "manual"
    label = "Manual / offline settlement"
    is_offline = True

    def is_configured(self) -> bool:
        """Always available, but never live."""
        return True

    def create_order(
        self, *, amount: Decimal, currency: str, reference: str, notes: dict[str, Any]
    ) -> GatewayOrder:
        """Return a local reference so the intent can be tracked."""
        return GatewayOrder(
            gateway_order_id=generate_reference("MAN", 12),
            amount=amount,
            currency=currency,
            checkout_payload={},
            raw={"gateway": "manual", "reference": reference, "requires_manual_confirmation": True},
        )

    def verify_payment(self, payload: dict[str, Any]) -> GatewayVerification:
        """Refuse to confirm. Only a human, with a bank statement, can."""
        return GatewayVerification(
            is_valid=False,
            gateway_order_id=str(payload.get("gateway_order_id", "")),
            failure_reason=(
                "This payment method is not integrated yet. The order is on hold "
                "until the payment is confirmed manually."
            ),
            raw={"gateway": "manual"},
        )

    def capture_payment(
        self, *, gateway_payment_id: str, amount: Decimal, currency: str
    ) -> dict[str, Any]:
        """Nothing to capture."""
        return {"status": "pending", "gateway": "manual"}

    def refund(
        self,
        *,
        gateway_payment_id: str,
        amount: Decimal,
        currency: str,
        notes: dict[str, Any],
    ) -> GatewayRefund:
        """Refuse. There is nothing to reverse."""
        raise GatewayError(
            "This payment method is not integrated. Issue the refund manually and "
            "record it against the order."
        )

    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """No provider, no webhooks."""
        raise GatewayError("This payment method does not send webhooks.")

    def supports_refunds(self) -> bool:
        """Refunds happen outside the platform."""
        return False
