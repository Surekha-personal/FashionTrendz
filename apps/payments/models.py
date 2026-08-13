"""Payment models.

Four models:

* :class:`Payment` — one payment intent against an order. An order may have
  several: a declined card followed by a successful UPI is two payments, not
  one row overwritten twice. Overwriting loses the decline, which is exactly
  what a chargeback investigation asks for.
* :class:`PaymentAttempt` — the individual tries within one intent.
* :class:`Refund` — money given back, in whole or in part.
* :class:`PaymentWebhookLog` — every webhook received. This table is what makes
  processing idempotent, and it is the audit trail when a provider and the
  store disagree about what happened.

Every gateway response is stored raw in a ``JSONField``. Storage is cheap;
reconstructing what a provider actually said, six months later, from parsed
columns that turned out to be the wrong ones, is not.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import DEFAULT_CURRENCY, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS
from apps.core.mixins import BaseModel
from apps.payments.managers import PaymentManager, RefundManager, WebhookLogManager
from apps.payments.validators import gateway_id_validator, validate_positive_amount


class PaymentState(models.TextChoices):
    """Lifecycle of one payment intent.

    Distinct from ``core.choices.PaymentStatus``, which describes the *order's*
    overall settlement. One order with a failed card and a successful UPI has
    two payments — one FAILED, one CAPTURED — and an order status of PAID.
    Collapsing them would make the failure invisible.
    """

    CREATED = "created", _("Created")
    AUTHORISED = "authorised", _("Authorised")
    CAPTURED = "captured", _("Captured")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")
    REFUNDED = "refunded", _("Refunded")
    PARTIALLY_REFUNDED = "partially_refunded", _("Partially refunded")


class AttemptState(models.TextChoices):
    """Outcome of one try within a payment intent."""

    STARTED = "started", _("Started")
    SUCCEEDED = "succeeded", _("Succeeded")
    FAILED = "failed", _("Failed")
    ABANDONED = "abandoned", _("Abandoned")


class RefundState(models.TextChoices):
    """Lifecycle of a refund."""

    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    PROCESSED = "processed", _("Processed")
    FAILED = "failed", _("Failed")


class RefundReason(models.TextChoices):
    """Why money is being returned.

    Stored because the finance report treats them differently: a cancellation
    refund is a sale that never happened, a return refund is a sale reversed,
    and a goodwill refund is a marketing cost.
    """

    ORDER_CANCELLED = "order_cancelled", _("Order cancelled")
    ORDER_RETURNED = "order_returned", _("Order returned")
    ITEM_UNAVAILABLE = "item_unavailable", _("Item unavailable")
    DAMAGED = "damaged", _("Damaged on arrival")
    GOODWILL = "goodwill", _("Goodwill gesture")
    DUPLICATE = "duplicate", _("Duplicate payment")
    OTHER = "other", _("Other")


class Payment(BaseModel):
    """One payment intent against an order."""

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name=_("order"),
    )

    gateway = models.CharField(
        _("gateway"),
        max_length=32,
        db_index=True,
        help_text=_("Registry key, e.g. razorpay or cod."),
    )
    method = models.CharField(
        _("method"),
        max_length=32,
        blank=True,
        help_text=_("How the customer paid, as reported by the gateway."),
    )

    # -- Gateway identifiers ------------------------------------------------

    gateway_order_id = models.CharField(
        _("gateway order id"),
        max_length=100,
        blank=True,
        db_index=True,
        validators=[gateway_id_validator],
    )
    gateway_payment_id = models.CharField(
        _("gateway payment id"),
        max_length=100,
        blank=True,
        db_index=True,
        validators=[gateway_id_validator],
    )
    gateway_signature = models.CharField(
        _("gateway signature"),
        max_length=255,
        blank=True,
        help_text=_("Kept for dispute evidence — it proves the callback was genuine."),
    )
    transaction_id = models.CharField(
        _("transaction id"), max_length=100, blank=True, db_index=True
    )
    reference_number = models.CharField(
        _("reference number"),
        max_length=64,
        blank=True,
        help_text=_("Bank or UPI reference the customer sees on their statement."),
    )

    # -- Money --------------------------------------------------------------

    amount = models.DecimalField(
        _("amount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[validate_positive_amount],
    )
    refunded_amount = models.DecimalField(
        _("refunded amount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        editable=False,
    )
    currency = models.CharField(
        _("currency"), max_length=3, default=DEFAULT_CURRENCY
    )

    status = models.CharField(
        _("status"),
        max_length=24,
        choices=PaymentState.choices,
        default=PaymentState.CREATED,
        db_index=True,
    )
    failure_reason = models.CharField(_("failure reason"), max_length=255, blank=True)

    captured_at = models.DateTimeField(_("captured at"), null=True, blank=True)
    raw_response = models.JSONField(
        _("raw gateway response"),
        default=dict,
        blank=True,
        help_text=_("Verbatim provider payload, for disputes and debugging."),
    )

    objects = PaymentManager()

    class Meta:
        verbose_name = _("payment")
        verbose_name_plural = _("payments")
        ordering = ["-created_at"]
        constraints = [
            # A gateway payment id identifies exactly one payment. Without
            # this, a replayed webhook or a double-submitted callback creates a
            # second row and the order looks paid for twice.
            models.UniqueConstraint(
                fields=["gateway", "gateway_payment_id"],
                condition=models.Q(gateway_payment_id__gt=""),
                name="unique_gateway_payment_id",
            ),
            models.UniqueConstraint(
                fields=["gateway", "gateway_order_id"],
                condition=models.Q(gateway_order_id__gt=""),
                name="unique_gateway_order_id",
            ),
            # Refunding more than was paid has no automatic remedy.
            models.CheckConstraint(
                condition=models.Q(refunded_amount__lte=models.F("amount")),
                name="payment_refund_within_amount",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="payment_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["order", "-created_at"], name="payment_order_idx"),
            models.Index(fields=["status", "-created_at"], name="payment_status_idx"),
            models.Index(fields=["gateway", "status"], name="payment_gateway_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.gateway}:{self.gateway_payment_id or self.gateway_order_id or self.pk}"

    @property
    def is_captured(self) -> bool:
        """Return whether the money has settled."""
        return self.status == PaymentState.CAPTURED

    @property
    def refundable_amount(self) -> Decimal:
        """Return how much of this payment can still be given back."""
        if self.status not in {
            PaymentState.CAPTURED,
            PaymentState.PARTIALLY_REFUNDED,
        }:
            return Decimal("0.00")
        return max(self.amount - self.refunded_amount, Decimal("0.00"))

    @property
    def is_fully_refunded(self) -> bool:
        """Return whether everything has been given back."""
        return self.refunded_amount >= self.amount

    @property
    def attempt_count(self) -> int:
        """Return how many times the customer tried to pay."""
        return self.attempts.count()


class PaymentAttempt(BaseModel):
    """One try within a payment intent.

    A customer who mistypes a CVV twice before succeeding produces three
    attempts against one payment. Keeping them is what turns "the payment
    failed" into "the card was declined twice for insufficient funds" when
    support asks.
    """

    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name="attempts",
        verbose_name=_("payment"),
    )

    attempt_number = models.PositiveSmallIntegerField(_("attempt number"), default=1)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=AttemptState.choices,
        default=AttemptState.STARTED,
        db_index=True,
    )
    failure_reason = models.CharField(_("failure reason"), max_length=255, blank=True)
    failure_code = models.CharField(_("failure code"), max_length=64, blank=True)
    retry_count = models.PositiveSmallIntegerField(_("retry count"), default=0)
    gateway_response = models.JSONField(
        _("gateway response"), default=dict, blank=True
    )

    class Meta:
        verbose_name = _("payment attempt")
        verbose_name_plural = _("payment attempts")
        ordering = ["payment", "attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "attempt_number"],
                name="unique_attempt_number_per_payment",
            ),
        ]
        indexes = [
            models.Index(fields=["payment", "attempt_number"], name="attempt_payment_idx"),
        ]

    def __str__(self) -> str:
        return f"Attempt {self.attempt_number} on {self.payment}"


class Refund(BaseModel):
    """Money returned to a customer, in whole or in part."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("payment"),
    )

    amount = models.DecimalField(
        _("refund amount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        validators=[validate_positive_amount],
    )
    currency = models.CharField(_("currency"), max_length=3, default=DEFAULT_CURRENCY)

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=RefundState.choices,
        default=RefundState.PENDING,
        db_index=True,
    )
    reason = models.CharField(
        _("reason"),
        max_length=24,
        choices=RefundReason.choices,
        default=RefundReason.OTHER,
        db_index=True,
    )
    notes = models.CharField(_("notes"), max_length=255, blank=True)

    gateway_refund_id = models.CharField(
        _("gateway refund id"), max_length=100, blank=True, db_index=True
    )
    reference_number = models.CharField(
        _("reference number"),
        max_length=64,
        blank=True,
        help_text=_("What the customer will see on their statement."),
    )

    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)
    raw_response = models.JSONField(_("raw gateway response"), default=dict, blank=True)

    objects = RefundManager()

    class Meta:
        verbose_name = _("refund")
        verbose_name_plural = _("refunds")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway_refund_id"],
                condition=models.Q(gateway_refund_id__gt=""),
                name="unique_gateway_refund_id",
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=Decimal("0")),
                name="refund_amount_positive",
            ),
        ]
        indexes = [
            models.Index(fields=["payment", "-created_at"], name="refund_payment_idx"),
            models.Index(fields=["status", "-created_at"], name="refund_status_idx"),
        ]

    def __str__(self) -> str:
        return f"Refund {self.currency} {self.amount} on {self.payment}"

    @property
    def is_complete(self) -> bool:
        """Return whether the customer has the money."""
        return self.status == RefundState.PROCESSED

    @property
    def is_partial(self) -> bool:
        """Return whether this refund covers less than the whole payment."""
        return self.amount < self.payment.amount


class PaymentWebhookLog(BaseModel):
    """One webhook received from a gateway.

    The reason this table exists is the unique constraint on
    ``(gateway, event_id)``. Providers retry aggressively — Razorpay resends an
    unacknowledged event for 24 hours — and without a uniqueness check, five
    retries of "payment.captured" mark an order paid five times and, worse,
    could issue five refunds.

    Inserting the log row *first*, and treating the ``IntegrityError`` as "seen
    already", makes the whole handler idempotent with no extra locking.
    """

    gateway = models.CharField(_("gateway"), max_length=32, db_index=True)
    event_id = models.CharField(
        _("event id"),
        max_length=200,
        db_index=True,
        help_text=_("Provider's stable id for this event. The idempotency key."),
    )
    event_type = models.CharField(_("event type"), max_length=64, db_index=True)

    signature = models.CharField(_("signature"), max_length=255, blank=True)
    is_verified = models.BooleanField(_("signature verified"), default=False)
    is_duplicate = models.BooleanField(
        _("duplicate"),
        default=False,
        db_index=True,
        help_text=_("The provider re-sent an event already processed."),
    )

    payload = models.JSONField(_("payload"), default=dict, blank=True)
    headers = models.JSONField(_("headers"), default=dict, blank=True)

    processed_at = models.DateTimeField(_("processed at"), null=True, blank=True)
    error = models.TextField(
        _("processing error"),
        blank=True,
        help_text=_("Stack summary when handling raised. Non-empty means unapplied."),
    )

    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        related_name="webhook_logs",
        null=True,
        blank=True,
        verbose_name=_("payment"),
    )

    objects = WebhookLogManager()

    class Meta:
        verbose_name = _("payment webhook log")
        verbose_name_plural = _("payment webhook logs")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["gateway", "event_id"], name="unique_webhook_event"
            ),
        ]
        indexes = [
            models.Index(fields=["gateway", "event_type"], name="webhook_type_idx"),
            models.Index(fields=["-created_at"], name="webhook_recent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.gateway}:{self.event_type}:{self.event_id}"

    @property
    def is_processed(self) -> bool:
        """Return whether this event has been applied."""
        return self.processed_at is not None

    def mark_processed(self, error: str = "") -> None:
        """Stamp the event as handled, recording any failure."""
        self.processed_at = timezone.now()
        self.error = error[:2000]
        self.save(update_fields=["processed_at", "error", "updated_at"])
