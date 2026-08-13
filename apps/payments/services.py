"""Payment business logic.

Three flows: create a payment, verify one, refund one. Plus the webhook
handler, which is the only part that runs without a user watching and therefore
the part that has to be right on its own.

Rules the module keeps:

* **Never trust the client.** The browser reports success; the gateway proves
  it. Verification always ends in a signature check or an API read.
* **Every webhook is idempotent.** The log row is inserted first; a duplicate
  event id makes the insert fail, and that failure *is* the duplicate check.
* **Amounts are checked against the order, not the request.** A callback
  claiming ₹1 for a ₹15,000 order is rejected.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.core.choices import OrderStatus, PaymentStatus
from apps.core.exceptions import BusinessRuleViolation, ResourceConflict
from apps.core.logging import get_logger
from apps.core.utils import quantise_money
from apps.orders.models import Order
from apps.orders.services import mark_payment_settled, transition_order
from apps.payments.gateways import GatewayError, SignatureError, get_gateway
from apps.payments.gateways.base import WebhookEvent
from apps.payments.models import (
    AttemptState,
    Payment,
    PaymentAttempt,
    PaymentState,
    PaymentWebhookLog,
    Refund,
    RefundReason,
    RefundState,
)
from apps.payments.validators import validate_refund_amount

logger = get_logger(__name__)

#: How far a reported amount may differ from the order total before it is
#: rejected. Zero — the gateway echoes back what we sent, and any drift is
#: either a bug or tampering.
AMOUNT_TOLERANCE = Decimal("0.00")


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


@transaction.atomic
def create_payment(order: Order, gateway_code: str | None = None) -> Payment:
    """Create a payment intent for an order and return it.

    Reuses an existing unfinished intent rather than making a second one: a
    customer who reloads the checkout page must not leave a trail of orphaned
    gateway orders, each of which the provider will chase for reconciliation.
    """
    # Re-read from the database rather than trusting the passed instance: a
    # caller holding an Order fetched before a cancellation would otherwise
    # open a payment intent for an order that no longer exists to be paid for.
    order.refresh_from_db(fields=["status", "payment_status"])

    if order.payment_status == PaymentStatus.PAID:
        raise BusinessRuleViolation("This order has already been paid for.")

    if order.status in {OrderStatus.CANCELLED, OrderStatus.REFUNDED}:
        raise BusinessRuleViolation("This order can no longer be paid for.")

    code = (gateway_code or order.payment_method or "cod").lower()
    gateway = get_gateway(code)

    existing = (
        Payment.objects.filter(order=order, gateway=code, status=PaymentState.CREATED)
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        _open_attempt(existing)
        return existing

    intent = gateway.create_order(
        amount=order.grand_total,
        currency=order.currency,
        reference=order.order_number,
        notes={
            "order_number": order.order_number,
            "customer": order.user.email,
        },
    )

    payment = Payment.objects.create(
        order=order,
        gateway=code,
        method=order.payment_method,
        gateway_order_id=intent.gateway_order_id,
        amount=order.grand_total,
        currency=order.currency,
        status=PaymentState.CREATED,
        raw_response=intent.raw,
    )
    _open_attempt(payment)

    logger.info(
        "payment created order=%s gateway=%s amount=%s",
        order.order_number,
        code,
        order.grand_total,
    )
    return payment


def get_checkout_payload(payment: Payment) -> dict[str, Any]:
    """Return what the browser needs to open the gateway's widget."""
    gateway = get_gateway(payment.gateway)

    if gateway.is_offline:
        return {}

    raw = payment.raw_response or {}
    return {
        "key": getattr(gateway, "key_id", ""),
        "order_id": payment.gateway_order_id,
        "amount": raw.get("amount"),
        "currency": payment.currency,
        "name": "Fashion Trendz",
        "description": payment.order.order_number,
    }


def _open_attempt(payment: Payment) -> PaymentAttempt:
    """Open a new attempt row for a payment."""
    number = payment.attempts.count() + 1
    return PaymentAttempt.objects.create(
        payment=payment, attempt_number=number, status=AttemptState.STARTED
    )


def _close_attempt(
    payment: Payment, *, succeeded: bool, reason: str = "", response: dict[str, Any] | None = None
) -> None:
    """Close the newest open attempt with an outcome."""
    attempt = payment.attempts.filter(status=AttemptState.STARTED).order_by(
        "-attempt_number"
    ).first()
    if attempt is None:
        attempt = _open_attempt(payment)

    attempt.status = AttemptState.SUCCEEDED if succeeded else AttemptState.FAILED
    attempt.failure_reason = reason[:255]
    attempt.gateway_response = response or {}
    attempt.retry_count = max(attempt.attempt_number - 1, 0)
    attempt.save(
        update_fields=[
            "status",
            "failure_reason",
            "gateway_response",
            "retry_count",
            "updated_at",
        ]
    )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@transaction.atomic
def verify_payment(payload: dict[str, Any], user: Any = None) -> Payment:
    """Verify a payment the browser reports as complete.

    The security boundary of the whole module. Three things are proved before
    an order is marked paid:

    1. the signature is genuine (the message really came from the gateway);
    2. the gateway itself says the payment is captured;
    3. the amount matches the order.

    Any one of them failing marks the payment failed and leaves the order
    unpaid. Skipping (3) is how a forged-but-correctly-signed ₹1 payment
    settles a ₹15,000 order — the signature only proves the message is
    authentic, not that the numbers are right.
    """
    gateway_order_id = payload.get("razorpay_order_id") or payload.get("gateway_order_id")
    if not gateway_order_id:
        raise BusinessRuleViolation("The payment response is incomplete.")

    payment = (
        Payment.objects.select_for_update()
        .filter(gateway_order_id=gateway_order_id)
        .select_related("order")
        .first()
    )
    if payment is None:
        raise BusinessRuleViolation("No payment found for that reference.")

    if user is not None and payment.order.user_id != user.pk and not user.is_staff:
        # Scoped like every other order read: a stranger's payment is invisible.
        raise BusinessRuleViolation("No payment found for that reference.")

    if payment.status == PaymentState.CAPTURED:
        # A double-submitted callback. The payment is already settled; saying
        # so is correct and idempotent.
        return payment

    gateway = get_gateway(payment.gateway)
    verification = gateway.verify_payment(payload)

    if not verification.is_valid:
        return _fail_payment(payment, verification.failure_reason, verification.raw)

    if verification.amount is not None:
        expected = quantise_money(payment.amount, payment.currency)
        actual = quantise_money(verification.amount, payment.currency)
        if abs(actual - expected) > AMOUNT_TOLERANCE:
            logger.error(
                "payment amount mismatch order=%s expected=%s got=%s",
                payment.order.order_number,
                expected,
                actual,
            )
            return _fail_payment(
                payment,
                f"Amount mismatch: expected {expected}, gateway reported {actual}.",
                verification.raw,
            )

    return _capture_payment(payment, verification)


def _capture_payment(payment: Payment, verification: Any) -> Payment:
    """Mark a payment captured and settle its order."""
    payment.status = PaymentState.CAPTURED
    payment.gateway_payment_id = verification.gateway_payment_id
    payment.gateway_signature = verification.signature
    payment.transaction_id = verification.gateway_payment_id
    payment.method = verification.method or payment.method
    payment.captured_at = timezone.now()
    payment.raw_response = verification.raw or payment.raw_response
    payment.failure_reason = ""
    payment.save(
        update_fields=[
            "status",
            "gateway_payment_id",
            "gateway_signature",
            "transaction_id",
            "method",
            "captured_at",
            "raw_response",
            "failure_reason",
            "updated_at",
        ]
    )

    _close_attempt(payment, succeeded=True, response=verification.raw)

    # Hand off to the orders module's own entry point rather than writing
    # Order.status here — that keeps the state machine and its audit trail the
    # single writer of order state.
    mark_payment_settled(
        payment.order, reference=payment.gateway_payment_id, confirm=True
    )

    logger.info(
        "payment captured order=%s payment=%s amount=%s",
        payment.order.order_number,
        payment.gateway_payment_id,
        payment.amount,
    )
    return payment


def _fail_payment(payment: Payment, reason: str, response: dict[str, Any]) -> Payment:
    """Mark a payment failed, leaving the order unpaid and retryable."""
    payment.status = PaymentState.FAILED
    payment.failure_reason = (reason or "Payment failed.")[:255]
    payment.raw_response = response or payment.raw_response
    payment.save(
        update_fields=["status", "failure_reason", "raw_response", "updated_at"]
    )

    _close_attempt(payment, succeeded=False, reason=reason, response=response)

    logger.warning(
        "payment failed order=%s reason=%s", payment.order.order_number, reason
    )
    return payment


# ---------------------------------------------------------------------------
# Refunds
# ---------------------------------------------------------------------------


def create_refund(
    payment: Payment,
    *,
    amount: Decimal | None = None,
    reason: str = RefundReason.OTHER,
    notes: str = "",
    initiated_by: Any = None,
) -> Refund:
    """Refund all or part of a captured payment.

    ``amount`` defaults to everything still refundable, which is what
    "cancel and refund" means.

    Three phases, deliberately **not** one transaction:

    1. *reserve* — under a row lock, validate and add the amount to
       ``refunded_amount`` straight away, then commit. The reservation is what
       makes concurrency safe: two simultaneous partial refunds cannot both
       decide there is room, because the second one sees the first's write.
    2. *call the gateway* — outside any transaction, because a network round
       trip must never be holding a lock on a money row.
    3. *settle* — record the outcome; on failure, release the reservation.

    Wrapping all three in one ``atomic`` block would be simpler and wrong: a
    gateway failure would roll back the ``Refund`` row along with everything
    else, leaving no record that a refund was ever attempted. An operator
    needs to see the attempt.
    """
    from django.core.exceptions import ValidationError as DjangoValidationError

    with transaction.atomic():
        locked = (
            Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
        )

        if locked.status not in {PaymentState.CAPTURED, PaymentState.PARTIALLY_REFUNDED}:
            raise BusinessRuleViolation("Only captured payments can be refunded.")

        gateway = get_gateway(locked.gateway)
        if not gateway.supports_refunds():
            raise BusinessRuleViolation(
                f"{gateway.label} refunds are handled outside the platform. "
                "Record the transfer manually."
            )

        requested = quantise_money(
            amount if amount is not None else locked.refundable_amount, locked.currency
        )

        try:
            validate_refund_amount(requested, locked.amount, locked.refunded_amount)
        except DjangoValidationError as exc:
            raise BusinessRuleViolation(exc.messages[0]) from exc

        refund = Refund.objects.create(
            payment=locked,
            amount=requested,
            currency=locked.currency,
            status=RefundState.PENDING,
            reason=reason,
            notes=notes[:255],
        )
        _reserve_refund(locked, requested)

    try:
        result = gateway.refund(
            gateway_payment_id=locked.gateway_payment_id,
            amount=requested,
            currency=locked.currency,
            notes={
                "order_number": locked.order.order_number,
                "refund_id": str(refund.uuid),
                "reason": reason,
            },
        )
    except GatewayError as exc:
        with transaction.atomic():
            _release_refund(locked, requested)
            Refund.objects.filter(pk=refund.pk).update(
                status=RefundState.FAILED,
                notes=f"{notes} | gateway error: {exc.detail}"[:255],
            )
        logger.error(
            "refund failed order=%s amount=%s error=%s",
            locked.order.order_number,
            requested,
            exc.detail,
        )
        raise

    with transaction.atomic():
        refund.gateway_refund_id = result.refund_id
        refund.raw_response = result.raw
        refund.status = (
            RefundState.PROCESSED
            if result.status == "processed"
            else RefundState.PROCESSING
        )
        if refund.status == RefundState.PROCESSED:
            refund.processed_at = timezone.now()
        refund.save(
            update_fields=[
                "gateway_refund_id",
                "raw_response",
                "status",
                "processed_at",
                "updated_at",
            ]
        )
        _sync_payment_refund_status(locked)

    logger.info(
        "refund created order=%s amount=%s reason=%s by=%s",
        locked.order.order_number,
        requested,
        reason,
        getattr(initiated_by, "pk", None),
    )
    return refund


def _reserve_refund(payment: Payment, amount: Decimal) -> None:
    """Claim ``amount`` against the payment before calling the gateway.

    ``F()`` so concurrent refunds accumulate rather than overwrite, and the
    conditional WHERE means the database refuses a reservation that would
    exceed the payment — the same shape as the stock reservation in checkout.
    """
    updated = Payment.objects.filter(
        pk=payment.pk, refunded_amount__lte=F("amount") - amount
    ).update(refunded_amount=F("refunded_amount") + amount)

    if not updated:
        raise BusinessRuleViolation(
            "Another refund for this payment is already in progress."
        )

    payment.refresh_from_db(fields=["refunded_amount"])
    _sync_payment_refund_status(payment)


def _release_refund(payment: Payment, amount: Decimal) -> None:
    """Give back a reservation whose gateway call failed."""
    Payment.objects.filter(pk=payment.pk, refunded_amount__gte=amount).update(
        refunded_amount=F("refunded_amount") - amount
    )
    payment.refresh_from_db(fields=["refunded_amount"])
    _sync_payment_refund_status(payment)


def _sync_payment_refund_status(payment: Payment) -> None:
    """Move the payment's status to match how much has been refunded."""
    if payment.refunded_amount <= 0:
        status = PaymentState.CAPTURED
        order_status = PaymentStatus.PAID
    elif payment.refunded_amount >= payment.amount:
        status = PaymentState.REFUNDED
        order_status = PaymentStatus.REFUNDED
    else:
        status = PaymentState.PARTIALLY_REFUNDED
        order_status = PaymentStatus.PARTIALLY_REFUNDED

    Payment.objects.filter(pk=payment.pk).update(status=status)
    payment.status = status
    Order.objects.filter(pk=payment.order_id).update(payment_status=order_status)


@transaction.atomic
def refund_order(
    order: Order,
    *,
    amount: Decimal | None = None,
    reason: str = RefundReason.ORDER_CANCELLED,
    notes: str = "",
    initiated_by: Any = None,
) -> Refund:
    """Refund an order through whichever payment settled it."""
    payment = (
        Payment.objects.filter(order=order)
        .successful()
        .order_by("-captured_at")
        .first()
    ) or Payment.objects.filter(
        order=order, status=PaymentState.PARTIALLY_REFUNDED
    ).first()

    if payment is None:
        raise BusinessRuleViolation(
            "No settled payment was found for this order. "
            "Cash-on-delivery orders are refunded outside the platform."
        )

    return create_refund(
        payment, amount=amount, reason=reason, notes=notes, initiated_by=initiated_by
    )


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def handle_webhook(gateway_code: str, body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    """Verify, log and apply one webhook.

    The order of operations is the whole design:

    1. **verify the signature** — an unverified webhook is a stranger claiming
       an order was paid for;
    2. **insert the log row** — the unique ``(gateway, event_id)`` constraint
       turns a provider retry into an ``IntegrityError``, which *is* the
       duplicate check. No extra lock, no read-then-write race;
    3. **apply the effect** inside its own transaction, recording any error on
       the log row rather than raising.

    Always returns 200-shaped data, even for a duplicate or an unhandled event.
    Returning an error makes the provider retry forever, and a webhook we
    simply do not implement is not an error.
    """
    gateway = get_gateway(gateway_code)

    try:
        event = gateway.verify_webhook(body, headers)
    except SignatureError:
        # Logged as a security event, then re-raised: a bad signature must not
        # be acknowledged, or an attacker learns nothing stops them retrying.
        logger.warning("webhook signature rejected gateway=%s", gateway_code)
        raise

    try:
        with transaction.atomic():
            log = PaymentWebhookLog.objects.create(
                gateway=gateway_code,
                event_id=event.event_id,
                event_type=event.event_type,
                signature=str(headers.get("X-Razorpay-Signature", ""))[:255],
                is_verified=True,
                payload=event.raw,
                headers={k: v for k, v in headers.items() if k.lower().startswith("x-")},
            )
    except IntegrityError:
        PaymentWebhookLog.objects.filter(
            gateway=gateway_code, event_id=event.event_id
        ).update(is_duplicate=True)
        logger.info(
            "duplicate webhook ignored gateway=%s event=%s",
            gateway_code,
            event.event_id,
        )
        return {"status": "duplicate", "event_id": event.event_id, "applied": False}

    try:
        applied = _apply_event(event, log)
        log.mark_processed()
    except Exception as exc:  # noqa: BLE001 - recorded, never re-raised
        logger.exception("webhook processing failed event=%s", event.event_id)
        log.mark_processed(error=f"{type(exc).__name__}: {exc}")
        return {"status": "error", "event_id": event.event_id, "applied": False}

    return {"status": "processed", "event_id": event.event_id, "applied": applied}


def _apply_event(event: WebhookEvent, log: PaymentWebhookLog) -> bool:
    """Apply one verified event, returning whether it changed anything."""
    payment = _find_payment_for_event(event)

    if payment is not None:
        PaymentWebhookLog.objects.filter(pk=log.pk).update(payment=payment)

    if event.event_type in {"payment.captured", "order.paid"}:
        return _webhook_capture(event, payment)

    if event.event_type == "payment.failed":
        return _webhook_failure(event, payment)

    if event.event_type in {"refund.created", "refund.processed", "refund.failed"}:
        return _webhook_refund(event)

    logger.info("webhook event %s not handled", event.event_type)
    return False


def _find_payment_for_event(event: WebhookEvent) -> Payment | None:
    """Locate the payment an event refers to."""
    if event.gateway_payment_id:
        payment = Payment.objects.filter(
            gateway_payment_id=event.gateway_payment_id
        ).first()
        if payment is not None:
            return payment

    if event.gateway_order_id:
        return Payment.objects.filter(gateway_order_id=event.gateway_order_id).first()

    return None


@transaction.atomic
def _webhook_capture(event: WebhookEvent, payment: Payment | None) -> bool:
    """Settle a payment reported captured by the gateway.

    The safety net for the callback path: a customer who closes the tab the
    instant after paying never returns the browser callback, and this is what
    still marks their order paid.
    """
    if payment is None:
        logger.warning("capture webhook for unknown payment %s", event.gateway_payment_id)
        return False

    locked = Payment.objects.select_for_update().select_related("order").get(pk=payment.pk)
    if locked.status == PaymentState.CAPTURED:
        return False

    if event.amount is not None:
        expected = quantise_money(locked.amount, locked.currency)
        actual = quantise_money(event.amount, locked.currency)
        if abs(actual - expected) > AMOUNT_TOLERANCE:
            logger.error(
                "webhook amount mismatch payment=%s expected=%s got=%s",
                locked.pk,
                expected,
                actual,
            )
            return False

    locked.status = PaymentState.CAPTURED
    locked.gateway_payment_id = event.gateway_payment_id or locked.gateway_payment_id
    locked.transaction_id = locked.gateway_payment_id
    locked.captured_at = timezone.now()
    locked.raw_response = event.raw
    locked.save(
        update_fields=[
            "status",
            "gateway_payment_id",
            "transaction_id",
            "captured_at",
            "raw_response",
            "updated_at",
        ]
    )

    _close_attempt(locked, succeeded=True, response=event.raw)
    mark_payment_settled(locked.order, reference=locked.gateway_payment_id, confirm=True)
    return True


@transaction.atomic
def _webhook_failure(event: WebhookEvent, payment: Payment | None) -> bool:
    """Record a payment the gateway reports as failed."""
    if payment is None:
        return False

    locked = Payment.objects.select_for_update().get(pk=payment.pk)
    if locked.status == PaymentState.CAPTURED:
        # A late failure event for a payment that did settle. Trust the
        # capture — reversing it here would unpay a real order.
        logger.warning("failure webhook for captured payment %s ignored", locked.pk)
        return False

    _fail_payment(locked, event.failure_reason or "Reported failed by gateway.", event.raw)
    return True


@transaction.atomic
def _webhook_refund(event: WebhookEvent) -> bool:
    """Update a refund's status from the gateway."""
    if not event.gateway_refund_id:
        return False

    refund = Refund.objects.filter(gateway_refund_id=event.gateway_refund_id).first()
    if refund is None:
        logger.warning("refund webhook for unknown refund %s", event.gateway_refund_id)
        return False

    if event.event_type == "refund.failed":
        refund.status = RefundState.FAILED
    elif event.status == "processed" or event.event_type == "refund.processed":
        refund.status = RefundState.PROCESSED
        refund.processed_at = timezone.now()
    else:
        refund.status = RefundState.PROCESSING

    refund.raw_response = event.raw
    refund.save(update_fields=["status", "processed_at", "raw_response", "updated_at"])
    return True


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_payments(user: Any) -> QuerySet[Payment]:
    """Return a customer's payments, newest first."""
    return Payment.objects.for_user(user).with_detail().order_by("-created_at")


def get_refunds(user: Any) -> QuerySet[Refund]:
    """Return a customer's refunds, newest first."""
    return Refund.objects.for_user(user).with_order().order_by("-created_at")


def get_payment_for_order(order: Order) -> Payment | None:
    """Return the payment that settled an order, if one did."""
    return Payment.objects.filter(order=order).successful().order_by("-captured_at").first()
