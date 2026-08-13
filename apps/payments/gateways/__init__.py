"""Payment gateway registry.

One import point for every gateway, so the rest of the codebase never names a
concrete provider. Switching from Razorpay to Stripe should be a settings
change and one new module here — not a search-and-replace through services.
"""

from __future__ import annotations

from django.conf import settings

from apps.payments.gateways.base import (
    BaseGateway,
    GatewayError,
    GatewayOrder,
    GatewayRefund,
    GatewayVerification,
    SignatureError,
    WebhookEvent,
)
from apps.payments.gateways.cod import CashOnDeliveryGateway
from apps.payments.gateways.manual import ManualGateway
from apps.payments.gateways.razorpay import RazorpayGateway

__all__ = [
    "BaseGateway",
    "GatewayError",
    "GatewayOrder",
    "GatewayRefund",
    "GatewayVerification",
    "SignatureError",
    "WebhookEvent",
    "get_gateway",
    "available_gateways",
    "GATEWAY_REGISTRY",
]

#: Every gateway the platform knows about, keyed by the code stored on
#: ``Payment.gateway``. Adding a provider means adding one entry here.
GATEWAY_REGISTRY: dict[str, type[BaseGateway]] = {
    "cod": CashOnDeliveryGateway,
    "razorpay": RazorpayGateway,
    # Stripe, PayU and Cashfree are not integrated. They resolve to the manual
    # gateway, which records the intent and leaves the payment pending rather
    # than pretending to charge anything — a stub that silently "succeeds" is
    # how a store ships orders nobody paid for.
    "stripe": ManualGateway,
    "payu": ManualGateway,
    "cashfree": ManualGateway,
}


def get_gateway(code: str) -> BaseGateway:
    """Return an instance of the gateway registered under ``code``."""
    gateway_class = GATEWAY_REGISTRY.get((code or "").lower())
    if gateway_class is None:
        raise GatewayError(f"Unknown payment gateway '{code}'.")
    return gateway_class()


def default_gateway_code() -> str:
    """Return the gateway used when the caller does not name one."""
    return getattr(settings, "PAYMENT_DEFAULT_GATEWAY", "razorpay")


def available_gateways() -> list[dict[str, object]]:
    """Return the gateways a checkout page may offer, with their readiness."""
    return [
        {
            "code": code,
            "label": gateway_class.label,
            "is_configured": gateway_class().is_configured(),
            "is_live": gateway_class is not ManualGateway,
        }
        for code, gateway_class in GATEWAY_REGISTRY.items()
    ]
