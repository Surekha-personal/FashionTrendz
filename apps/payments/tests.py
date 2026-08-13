"""Tests for the payments module.

The gateway is never contacted. Every test that would call Razorpay patches the
transport, so the suite is deterministic, offline and fast — and the two things
that must be right without a network, signature verification and webhook
idempotency, are tested against real HMACs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from django.db.utils import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.cart import services as cart_services
from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus, PaymentStatus
from apps.core.exceptions import BusinessRuleViolation
from apps.orders import services as order_services
from apps.payments import services
from apps.payments.gateways import get_gateway
from apps.payments.gateways.base import GatewayError, GatewayRefund, SignatureError
from apps.payments.gateways.razorpay import RazorpayGateway, from_paise, to_paise
from apps.payments.models import (
    Payment,
    PaymentState,
    PaymentWebhookLog,
    Refund,
    RefundReason,
    RefundState,
)
from apps.products.models import Product, ProductVariant, Size
from apps.users.models import Address, User

STRONG_PASSWORD = "Tr3ndz!Shopper42"
KEY_ID = "rzp_test_key"
KEY_SECRET = "rzp_test_secret"
WEBHOOK_SECRET = "whsec_test"

RAZORPAY_SETTINGS = {
    "RAZORPAY_KEY_ID": KEY_ID,
    "RAZORPAY_KEY_SECRET": KEY_SECRET,
    "RAZORPAY_WEBHOOK_SECRET": WEBHOOK_SECRET,
}


def sign(message: str, secret: str = KEY_SECRET) -> str:
    """Return the HMAC-SHA256 hex digest Razorpay would produce."""
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class PaymentFixtureMixin:
    """Builds a customer with an order ready to pay for."""

    def build_world(self) -> None:
        """Create the taxonomy, a product, a customer and an address."""
        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.brand = Brand.objects.create(name="Nordwyn")

        self.product = Product.objects.create(
            name="Classic Midi Dress", sku="FT-P0001",
            category=self.category, subcategory=self.subcategory, brand=self.brand,
            mrp=Decimal("2000.00"), selling_price=Decimal("2000.00"),
            published_at=timezone.now() - timezone.timedelta(days=1),
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, sku="FT-P0001-0", color="Navy", size=Size.M, stock=20
        )

        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Other"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com", password=STRONG_PASSWORD,
            first_name="Staff", is_staff=True,
        )
        self.address = Address.objects.create(
            user=self.user, full_name="Aditi Sharma", mobile="+919876543210",
            address_line_1="12 Linking Road", city="Mumbai", state="MH",
            country="India", postal_code="400050",
        )

    def place_order(self, method: str = "upi") -> Any:
        """Fill the bag and place an order."""
        cart = cart_services.get_or_create_cart(user=self.user)
        cart_services.add_to_cart(cart, self.product.slug, self.variant.sku, 1)
        return order_services.place_order(
            self.user, shipping_address_id=self.address.pk, payment_method=method
        )

    def make_payment(self, order: Any = None, **extra: Any) -> Payment:
        """Create a payment row without contacting a gateway."""
        target = order or self.place_order()
        defaults: dict[str, Any] = {
            "order": target,
            "gateway": "razorpay",
            "gateway_order_id": "order_TEST123456",
            "amount": target.grand_total,
            "currency": target.currency,
            "status": PaymentState.CREATED,
        }
        defaults.update(extra)
        return Payment.objects.create(**defaults)


class PaymentTestCase(PaymentFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Gateway abstraction
# ---------------------------------------------------------------------------


class GatewayRegistryTests(TestCase):
    """The registry and its placeholders."""

    def test_known_gateways_resolve(self) -> None:
        self.assertEqual(get_gateway("razorpay").code, "razorpay")
        self.assertEqual(get_gateway("cod").code, "cod")

    def test_an_unknown_gateway_raises(self) -> None:
        with self.assertRaises(GatewayError):
            get_gateway("bitcoin")

    def test_unintegrated_gateways_resolve_to_the_manual_stub(self) -> None:
        self.assertEqual(get_gateway("stripe").code, "manual")

    def test_the_manual_gateway_never_claims_success(self) -> None:
        # A stub that returns "captured" is how a store ships orders nobody
        # paid for.
        verification = get_gateway("stripe").verify_payment({"gateway_order_id": "x"})
        self.assertFalse(verification.is_valid)

    def test_cod_accepts_the_intent_without_claiming_the_money(self) -> None:
        verification = get_gateway("cod").verify_payment({"gateway_order_id": "x"})
        self.assertTrue(verification.is_valid)
        self.assertFalse(verification.raw["captured"])

    def test_cod_refunds_are_refused_loudly(self) -> None:
        # Silently returning "refunded" would close the ticket while the
        # customer is still out of pocket.
        with self.assertRaises(GatewayError):
            get_gateway("cod").refund(
                gateway_payment_id="x", amount=Decimal("100"), currency="INR", notes={}
            )

    @override_settings(**RAZORPAY_SETTINGS)
    def test_razorpay_reports_configured(self) -> None:
        self.assertTrue(RazorpayGateway().is_configured())

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_razorpay_reports_unconfigured(self) -> None:
        self.assertFalse(RazorpayGateway().is_configured())


class PaiseConversionTests(TestCase):
    """Currency unit conversion."""

    def test_rupees_to_paise(self) -> None:
        self.assertEqual(to_paise(Decimal("1999.00")), 199900)
        self.assertEqual(to_paise(Decimal("0.01")), 1)

    def test_the_classic_float_rounding_bug_is_avoided(self) -> None:
        # int(19.99 * 100) is 1998 in floating point. That missing paise is a
        # reconciliation failure nobody can explain a month later.
        self.assertEqual(to_paise(Decimal("19.99")), 1999)

    def test_paise_to_rupees(self) -> None:
        self.assertEqual(from_paise(199900), Decimal("1999.00"))
        self.assertEqual(from_paise(None), Decimal("0.00"))

    def test_conversion_round_trips(self) -> None:
        for value in ("1.00", "19.99", "2345.67", "99999.99"):
            self.assertEqual(from_paise(to_paise(Decimal(value))), Decimal(value))


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


@override_settings(**RAZORPAY_SETTINGS)
class SignatureVerificationTests(PaymentTestCase):
    """The security boundary."""

    def setUp(self) -> None:
        super().setUp()
        self.gateway = RazorpayGateway()

    def callback(self, order_id: str = "order_ABC", payment_id: str = "pay_XYZ") -> dict[str, str]:
        """Return a correctly signed browser callback."""
        return {
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sign(f"{order_id}|{payment_id}"),
        }

    @patch.object(RazorpayGateway, "_request")
    def test_a_valid_signature_verifies(self, request: Any) -> None:
        request.return_value = {"status": "captured", "amount": 200000, "method": "upi"}
        result = self.gateway.verify_payment(self.callback())

        self.assertTrue(result.is_valid)
        self.assertEqual(result.amount, Decimal("2000.00"))

    def test_a_forged_signature_is_rejected(self) -> None:
        payload = self.callback()
        payload["razorpay_signature"] = "0" * 64

        result = self.gateway.verify_payment(payload)
        self.assertFalse(result.is_valid)
        self.assertIn("Signature", result.failure_reason)

    def test_a_signature_from_the_wrong_secret_is_rejected(self) -> None:
        payload = self.callback()
        payload["razorpay_signature"] = sign("order_ABC|pay_XYZ", "wrong-secret")

        self.assertFalse(self.gateway.verify_payment(payload).is_valid)

    def test_tampering_with_the_payment_id_invalidates_the_signature(self) -> None:
        payload = self.callback()
        payload["razorpay_payment_id"] = "pay_SOMETHING_ELSE"

        self.assertFalse(self.gateway.verify_payment(payload).is_valid)

    def test_an_incomplete_callback_is_rejected(self) -> None:
        self.assertFalse(
            self.gateway.verify_payment({"razorpay_order_id": "order_ABC"}).is_valid
        )

    @patch.object(RazorpayGateway, "_request")
    def test_a_valid_signature_on_a_failed_payment_is_still_a_failure(
        self, request: Any
    ) -> None:
        # The signature proves the message is authentic, not that the payment
        # succeeded.
        request.return_value = {"status": "failed", "amount": 200000}
        self.assertFalse(self.gateway.verify_payment(self.callback()).is_valid)


@override_settings(**RAZORPAY_SETTINGS)
class WebhookSignatureTests(TestCase):
    """Webhook verification."""

    def setUp(self) -> None:
        self.gateway = RazorpayGateway()

    def event(self, event_type: str = "payment.captured") -> bytes:
        """Return a Razorpay webhook body."""
        return json.dumps(
            {
                "event": event_type,
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_XYZ",
                            "order_id": "order_ABC",
                            "amount": 200000,
                            "status": "captured",
                        }
                    }
                },
            }
        ).encode()

    def headers(self, body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
        """Return headers carrying a signature over ``body``."""
        return {
            "X-Razorpay-Signature": hmac.new(
                secret.encode(), body, hashlib.sha256
            ).hexdigest()
        }

    def test_a_valid_webhook_verifies_and_normalises(self) -> None:
        body = self.event()
        event = self.gateway.verify_webhook(body, self.headers(body))

        self.assertEqual(event.event_type, "payment.captured")
        self.assertEqual(event.gateway_payment_id, "pay_XYZ")
        self.assertEqual(event.amount, Decimal("2000.00"))

    def test_a_missing_signature_is_rejected(self) -> None:
        with self.assertRaises(SignatureError):
            self.gateway.verify_webhook(self.event(), {})

    def test_a_forged_signature_is_rejected(self) -> None:
        # An unverified webhook is a stranger claiming an order was paid for.
        with self.assertRaises(SignatureError):
            self.gateway.verify_webhook(
                self.event(), {"X-Razorpay-Signature": "0" * 64}
            )

    def test_the_webhook_secret_is_not_the_api_secret(self) -> None:
        # Signing with the API key is the classic misconfiguration.
        body = self.event()
        with self.assertRaises(SignatureError):
            self.gateway.verify_webhook(body, self.headers(body, KEY_SECRET))

    def test_a_modified_body_fails_verification(self) -> None:
        body = self.event()
        headers = self.headers(body)
        tampered = body.replace(b"200000", b"100")

        with self.assertRaises(SignatureError):
            self.gateway.verify_webhook(tampered, headers)

    def test_the_event_id_is_stable_across_retries(self) -> None:
        # Which is exactly what makes idempotency work.
        body = self.event()
        first = self.gateway.verify_webhook(body, self.headers(body))
        second = self.gateway.verify_webhook(body, self.headers(body))
        self.assertEqual(first.event_id, second.event_id)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="")
    def test_an_unconfigured_webhook_secret_raises(self) -> None:
        body = self.event()
        with self.assertRaises(GatewayError):
            self.gateway.verify_webhook(body, self.headers(body))


# ---------------------------------------------------------------------------
# Payment flow
# ---------------------------------------------------------------------------


@override_settings(**RAZORPAY_SETTINGS)
class CreatePaymentTests(PaymentTestCase):
    """Opening a payment intent."""

    @patch.object(RazorpayGateway, "_request")
    def test_a_payment_is_created(self, request: Any) -> None:
        request.return_value = {
            "id": "order_ABC", "amount": 209900, "currency": "INR", "notes": {}
        }
        order = self.place_order()
        payment = services.create_payment(order, "razorpay")

        self.assertEqual(payment.gateway_order_id, "order_ABC")
        self.assertEqual(payment.amount, order.grand_total)
        self.assertEqual(payment.status, PaymentState.CREATED)

    @patch.object(RazorpayGateway, "_request")
    def test_an_attempt_row_is_opened(self, request: Any) -> None:
        request.return_value = {"id": "order_ABC", "amount": 209900, "currency": "INR"}
        payment = services.create_payment(self.place_order(), "razorpay")
        self.assertEqual(payment.attempts.count(), 1)

    @patch.object(RazorpayGateway, "_request")
    def test_reloading_checkout_reuses_the_intent(self, request: Any) -> None:
        # Otherwise every page reload leaves an orphaned gateway order the
        # provider chases for reconciliation.
        request.return_value = {"id": "order_ABC", "amount": 209900, "currency": "INR"}
        order = self.place_order()

        first = services.create_payment(order, "razorpay")
        second = services.create_payment(order, "razorpay")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Payment.objects.filter(order=order).count(), 1)
        self.assertEqual(second.attempts.count(), 2)

    def test_cod_needs_no_network(self) -> None:
        order = self.place_order(method="cod")
        payment = services.create_payment(order, "cod")

        self.assertTrue(payment.gateway_order_id.startswith("COD-"))
        self.assertEqual(services.get_checkout_payload(payment), {})

    def test_an_already_paid_order_is_refused(self) -> None:
        order = self.place_order()
        order_services.mark_payment_settled(order, reference="pay_OLD")

        with self.assertRaises(BusinessRuleViolation):
            services.create_payment(order, "cod")

    def test_a_cancelled_order_cannot_be_paid_for(self) -> None:
        order = self.place_order()
        order_services.cancel_order(order, reason="Changed my mind")

        with self.assertRaises(BusinessRuleViolation):
            services.create_payment(order, "cod")

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_an_unconfigured_gateway_fails_at_the_boundary(self) -> None:
        with self.assertRaises(GatewayError):
            services.create_payment(self.place_order(), "razorpay")


@override_settings(**RAZORPAY_SETTINGS)
class VerifyPaymentTests(PaymentTestCase):
    """Verifying a completed payment."""

    def setUp(self) -> None:
        super().setUp()
        self.order = self.place_order()
        self.payment = self.make_payment(self.order, gateway_order_id="order_ABC")

    def callback(self, payment_id: str = "pay_XYZ") -> dict[str, str]:
        """Return a correctly signed callback for this payment."""
        return {
            "razorpay_order_id": "order_ABC",
            "razorpay_payment_id": payment_id,
            "razorpay_signature": sign(f"order_ABC|{payment_id}"),
        }

    @patch.object(RazorpayGateway, "_request")
    def test_a_verified_payment_settles_the_order(self, request: Any) -> None:
        request.return_value = {
            "status": "captured",
            "amount": to_paise(self.order.grand_total),
            "method": "upi",
        }
        payment = services.verify_payment(self.callback())

        self.assertEqual(payment.status, PaymentState.CAPTURED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)
        self.assertEqual(self.order.status, OrderStatus.CONFIRMED)

    @patch.object(RazorpayGateway, "_request")
    def test_the_attempt_is_closed_as_succeeded(self, request: Any) -> None:
        request.return_value = {
            "status": "captured", "amount": to_paise(self.order.grand_total)
        }
        services._open_attempt(self.payment)
        payment = services.verify_payment(self.callback())

        self.assertEqual(payment.attempts.first().status, "succeeded")

    def test_a_forged_signature_fails_the_payment(self) -> None:
        payload = self.callback()
        payload["razorpay_signature"] = "0" * 64

        payment = services.verify_payment(payload)

        self.assertEqual(payment.status, PaymentState.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    @patch.object(RazorpayGateway, "_request")
    def test_an_amount_mismatch_fails_the_payment(self, request: Any) -> None:
        # A correctly signed ₹1 payment must not settle a ₹2,000 order. The
        # signature proves authenticity, not that the numbers are right.
        request.return_value = {"status": "captured", "amount": 100, "method": "upi"}
        payment = services.verify_payment(self.callback())

        self.assertEqual(payment.status, PaymentState.FAILED)
        self.assertIn("mismatch", payment.failure_reason.lower())
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PENDING)

    @patch.object(RazorpayGateway, "_request")
    def test_verifying_twice_is_idempotent(self, request: Any) -> None:
        request.return_value = {
            "status": "captured", "amount": to_paise(self.order.grand_total)
        }
        first = services.verify_payment(self.callback())
        second = services.verify_payment(self.callback())

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(second.status, PaymentState.CAPTURED)

    def test_an_unknown_reference_is_rejected(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.verify_payment({"gateway_order_id": "order_NOPE"})

    def test_a_stranger_cannot_verify_someone_elses_payment(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.verify_payment(self.callback(), user=self.stranger)

    def test_the_same_gateway_payment_id_cannot_be_recorded_twice(self) -> None:
        Payment.objects.filter(pk=self.payment.pk).update(gateway_payment_id="pay_DUP")
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                order=self.order, gateway="razorpay", gateway_payment_id="pay_DUP",
                gateway_order_id="order_OTHER", amount=Decimal("100.00"),
            )


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


@override_settings(**RAZORPAY_SETTINGS)
class RefundTests(PaymentTestCase):
    """Giving money back."""

    def setUp(self) -> None:
        super().setUp()
        self.order = self.place_order()
        self.payment = self.make_payment(
            self.order,
            gateway_payment_id="pay_XYZ",
            status=PaymentState.CAPTURED,
            captured_at=timezone.now(),
        )

    def gateway_refund(self, amount: Decimal, refund_id: str = "rfnd_1") -> GatewayRefund:
        """Return what the gateway would report for a refund."""
        return GatewayRefund(
            refund_id=refund_id, amount=amount, status="processed", raw={}
        )

    @patch.object(RazorpayGateway, "refund")
    def test_a_full_refund(self, gateway_refund: Any) -> None:
        gateway_refund.return_value = self.gateway_refund(self.payment.amount)
        refund = services.create_refund(self.payment, reason=RefundReason.ORDER_CANCELLED)

        self.assertEqual(refund.amount, self.payment.amount)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentState.REFUNDED)
        self.assertTrue(self.payment.is_fully_refunded)

    @patch.object(RazorpayGateway, "refund")
    def test_a_partial_refund(self, gateway_refund: Any) -> None:
        gateway_refund.return_value = self.gateway_refund(Decimal("500.00"))
        refund = services.create_refund(self.payment, amount=Decimal("500.00"))

        self.assertTrue(refund.is_partial)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentState.PARTIALLY_REFUNDED)
        self.assertEqual(self.payment.refundable_amount, self.payment.amount - Decimal("500.00"))

    @patch.object(RazorpayGateway, "refund")
    def test_partial_refunds_accumulate(self, gateway_refund: Any) -> None:
        gateway_refund.side_effect = [
            self.gateway_refund(Decimal("300.00"), "rfnd_1"),
            self.gateway_refund(Decimal("200.00"), "rfnd_2"),
        ]
        services.create_refund(self.payment, amount=Decimal("300.00"))
        services.create_refund(self.payment, amount=Decimal("200.00"))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.refunded_amount, Decimal("500.00"))

    @patch.object(RazorpayGateway, "refund")
    def test_over_refunding_is_refused(self, gateway_refund: Any) -> None:
        # The one payment mistake with no automatic recovery.
        gateway_refund.return_value = self.gateway_refund(self.payment.amount)
        services.create_refund(self.payment)

        with self.assertRaises(BusinessRuleViolation):
            services.create_refund(self.payment, amount=Decimal("1.00"))

    def test_the_database_refuses_an_over_refund(self) -> None:
        with self.assertRaises(IntegrityError):
            Payment.objects.filter(pk=self.payment.pk).update(
                refunded_amount=self.payment.amount + Decimal("1.00")
            )

    def test_an_uncaptured_payment_cannot_be_refunded(self) -> None:
        pending = self.make_payment(
            self.place_order(), gateway_order_id="order_OTHER"
        )
        with self.assertRaises(BusinessRuleViolation):
            services.create_refund(pending)

    def test_cod_refunds_are_refused_with_an_explanation(self) -> None:
        cod_order = self.place_order(method="cod")
        cod_payment = self.make_payment(
            cod_order, gateway="cod", gateway_order_id="COD-123456",
            status=PaymentState.CAPTURED,
        )
        with self.assertRaises(BusinessRuleViolation) as caught:
            services.create_refund(cod_payment)
        self.assertIn("outside the platform", str(caught.exception.detail))

    @patch.object(RazorpayGateway, "refund")
    def test_a_gateway_failure_records_the_attempt(self, gateway_refund: Any) -> None:
        # An operator needs to see that a refund was tried and did not go through.
        gateway_refund.side_effect = GatewayError("Gateway down.")

        with self.assertRaises(GatewayError):
            services.create_refund(self.payment, amount=Decimal("100.00"))

        refund = Refund.objects.get(payment=self.payment)
        self.assertEqual(refund.status, RefundState.FAILED)

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.refunded_amount, Decimal("0.00"))

    @patch.object(RazorpayGateway, "refund")
    def test_refund_order_finds_the_settling_payment(self, gateway_refund: Any) -> None:
        gateway_refund.return_value = self.gateway_refund(self.payment.amount)
        refund = services.refund_order(self.order, reason=RefundReason.ORDER_RETURNED)
        self.assertEqual(refund.payment, self.payment)

    def test_refunding_an_unpaid_order_is_refused(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.refund_order(self.place_order())


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


@override_settings(**RAZORPAY_SETTINGS)
class WebhookProcessingTests(PaymentTestCase):
    """Idempotency and effect."""

    def setUp(self) -> None:
        super().setUp()
        self.order = self.place_order()
        self.payment = self.make_payment(
            self.order, gateway_order_id="order_ABC", gateway_payment_id="pay_XYZ"
        )

    def body(self, event_type: str = "payment.captured", amount: int | None = None) -> bytes:
        """Return a webhook body for this payment."""
        return json.dumps(
            {
                "event": event_type,
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_XYZ",
                            "order_id": "order_ABC",
                            "amount": amount if amount is not None else to_paise(self.order.grand_total),
                            "status": "captured",
                        }
                    }
                },
            }
        ).encode()

    def headers(self, body: bytes) -> dict[str, str]:
        """Return correctly signed webhook headers."""
        return {
            "X-Razorpay-Signature": hmac.new(
                WEBHOOK_SECRET.encode(), body, hashlib.sha256
            ).hexdigest()
        }

    def test_a_capture_webhook_settles_the_order(self) -> None:
        body = self.body()
        result = services.handle_webhook("razorpay", body, self.headers(body))

        self.assertEqual(result["status"], "processed")
        self.assertTrue(result["applied"])

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentState.CAPTURED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, PaymentStatus.PAID)

    def test_a_webhook_is_logged(self) -> None:
        body = self.body()
        services.handle_webhook("razorpay", body, self.headers(body))

        log = PaymentWebhookLog.objects.get()
        self.assertTrue(log.is_verified)
        self.assertTrue(log.is_processed)
        self.assertEqual(log.error, "")

    def test_a_duplicate_webhook_is_ignored(self) -> None:
        # Razorpay resends an unacknowledged event for 24 hours. Five retries
        # must not mark the order paid five times.
        body = self.body()
        headers = self.headers(body)

        first = services.handle_webhook("razorpay", body, headers)
        second = services.handle_webhook("razorpay", body, headers)
        third = services.handle_webhook("razorpay", body, headers)

        self.assertEqual(first["status"], "processed")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(third["status"], "duplicate")
        self.assertEqual(PaymentWebhookLog.objects.count(), 1)

    def test_a_duplicate_is_flagged_on_the_log(self) -> None:
        body = self.body()
        headers = self.headers(body)
        services.handle_webhook("razorpay", body, headers)
        services.handle_webhook("razorpay", body, headers)

        self.assertTrue(PaymentWebhookLog.objects.get().is_duplicate)

    def test_a_forged_webhook_is_rejected_and_not_logged(self) -> None:
        with self.assertRaises(SignatureError):
            services.handle_webhook(
                "razorpay", self.body(), {"X-Razorpay-Signature": "0" * 64}
            )
        self.assertEqual(PaymentWebhookLog.objects.count(), 0)

    def test_a_webhook_amount_mismatch_does_not_settle(self) -> None:
        body = self.body(amount=100)
        result = services.handle_webhook("razorpay", body, self.headers(body))

        self.assertFalse(result["applied"])
        self.payment.refresh_from_db()
        self.assertNotEqual(self.payment.status, PaymentState.CAPTURED)

    def test_a_failure_webhook_fails_the_payment(self) -> None:
        body = self.body("payment.failed")
        services.handle_webhook("razorpay", body, self.headers(body))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentState.FAILED)

    def test_a_late_failure_does_not_unpay_a_captured_payment(self) -> None:
        captured = self.body()
        services.handle_webhook("razorpay", captured, self.headers(captured))

        failed = self.body("payment.failed")
        services.handle_webhook("razorpay", failed, self.headers(failed))

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, PaymentState.CAPTURED)

    def test_an_unhandled_event_is_acknowledged_not_errored(self) -> None:
        # Returning an error makes the provider retry forever over something
        # that is not a failure.
        body = self.body("payment.dispute.created")
        result = services.handle_webhook("razorpay", body, self.headers(body))

        self.assertEqual(result["status"], "processed")
        self.assertFalse(result["applied"])

    def test_a_webhook_for_an_unknown_payment_is_recorded_and_ignored(self) -> None:
        payload = json.dumps(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {"id": "pay_UNKNOWN", "order_id": "order_UNKNOWN", "amount": 100}
                    }
                },
            }
        ).encode()
        result = services.handle_webhook("razorpay", payload, self.headers(payload))

        self.assertEqual(result["status"], "processed")
        self.assertFalse(result["applied"])

    def test_a_processing_error_is_recorded_not_raised(self) -> None:
        body = self.body()
        with patch.object(services, "_apply_event", side_effect=RuntimeError("boom")):
            result = services.handle_webhook("razorpay", body, self.headers(body))

        self.assertEqual(result["status"], "error")
        self.assertIn("boom", PaymentWebhookLog.objects.get().error)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@override_settings(**RAZORPAY_SETTINGS)
class PaymentAPITests(PaymentFixtureMixin, APITestCase):
    """/api/v1/payments/"""

    def setUp(self) -> None:
        self.build_world()
        self.client.force_authenticate(user=self.user)
        self.order = self.place_order()

    def test_authentication_is_required(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("payments:payment-create"),
            {"order_number": self.order.order_number},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch.object(RazorpayGateway, "_request")
    def test_create_payment_returns_the_checkout_payload(self, request: Any) -> None:
        request.return_value = {"id": "order_ABC", "amount": 209900, "currency": "INR"}
        response = self.client.post(
            reverse("payments:payment-create"),
            {"order_number": self.order.order_number, "gateway": "razorpay"},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()["data"]
        self.assertEqual(data["gateway"], "razorpay")
        self.assertFalse(data["is_offline"])
        self.assertEqual(data["checkout"]["order_id"], "order_ABC")

    def test_cod_returns_an_empty_checkout_payload(self) -> None:
        response = self.client.post(
            reverse("payments:payment-create"),
            {"order_number": self.order.order_number, "gateway": "cod"},
        )
        data = response.json()["data"]
        self.assertTrue(data["is_offline"])
        self.assertEqual(data["checkout"], {})

    def test_a_stranger_cannot_open_a_payment_for_another_order(self) -> None:
        self.client.force_authenticate(user=self.stranger)
        response = self.client.post(
            reverse("payments:payment-create"),
            {"order_number": self.order.order_number},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch.object(RazorpayGateway, "_request")
    def test_verify_endpoint_succeeds(self, request: Any) -> None:
        self.make_payment(self.order, gateway_order_id="order_ABC")
        request.return_value = {
            "status": "captured", "amount": to_paise(self.order.grand_total), "method": "upi"
        }

        response = self.client.post(
            reverse("payments:payment-verify"),
            {
                "razorpay_order_id": "order_ABC",
                "razorpay_payment_id": "pay_XYZ",
                "razorpay_signature": sign("order_ABC|pay_XYZ"),
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()["success"])

    def test_a_failed_verification_returns_402(self) -> None:
        # 402 rather than 400: the request was fine, the payment was not, and
        # the client should offer a retry.
        self.make_payment(self.order, gateway_order_id="order_ABC")
        response = self.client.post(
            reverse("payments:payment-verify"),
            {
                "razorpay_order_id": "order_ABC",
                "razorpay_payment_id": "pay_XYZ",
                "razorpay_signature": "0" * 64,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertFalse(response.json()["success"])

    def test_gateways_endpoint_is_public(self) -> None:
        self.client.force_authenticate(user=None)
        body = self.client.get(reverse("payments:payment-gateways")).json()

        codes = {row["code"] for row in body["data"]["gateways"]}
        self.assertIn("razorpay", codes)
        self.assertIn("cod", codes)

    def test_unintegrated_gateways_are_reported_as_not_live(self) -> None:
        body = self.client.get(reverse("payments:payment-gateways")).json()
        stripe = next(g for g in body["data"]["gateways"] if g["code"] == "stripe")
        self.assertFalse(stripe["is_live"])

    def test_a_customer_cannot_issue_a_refund(self) -> None:
        response = self.client.post(
            reverse("payments:payment-refund"),
            {"order_number": self.order.order_number},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch.object(RazorpayGateway, "refund")
    def test_staff_can_issue_a_refund(self, gateway_refund: Any) -> None:
        self.make_payment(
            self.order, gateway_payment_id="pay_XYZ", status=PaymentState.CAPTURED
        )
        gateway_refund.return_value = GatewayRefund(
            refund_id="rfnd_1", amount=self.order.grand_total, status="processed", raw={}
        )

        self.client.force_authenticate(user=self.staff)
        response = self.client.post(
            reverse("payments:payment-refund"),
            {"order_number": self.order.order_number, "reason": RefundReason.GOODWILL},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_payment_history_is_scoped_to_the_customer(self) -> None:
        self.make_payment(self.order, gateway_order_id="order_MINE")

        self.client.force_authenticate(user=self.stranger)
        body = self.client.get(reverse("payments:payment-list")).json()
        self.assertEqual(body["data"], [])

    def test_the_customer_payload_hides_the_raw_gateway_response(self) -> None:
        self.make_payment(self.order, gateway_order_id="order_MINE")
        body = self.client.get(reverse("payments:payment-list")).json()

        self.assertNotIn("raw_response", body["data"][0])
        self.assertNotIn("gateway_signature", body["data"][0])

    def test_the_webhook_endpoint_needs_no_authentication(self) -> None:
        # The signature is the authentication.
        body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
        signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("payments:payment-webhook-receive", args=["razorpay"]),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_forged_webhook_is_rejected_by_the_endpoint(self) -> None:
        body = json.dumps({"event": "payment.captured", "payload": {}}).encode()
        self.client.force_authenticate(user=None)
        response = self.client.post(
            reverse("payments:payment-webhook-receive", args=["razorpay"]),
            data=body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="0" * 64,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_refunds_endpoint_is_scoped(self) -> None:
        self.client.force_authenticate(user=self.stranger)
        body = self.client.get(reverse("payments:refund-list")).json()
        self.assertEqual(body["data"], [])
