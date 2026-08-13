"""Querysets and managers for the payments module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone


class PaymentQuerySet(models.QuerySet):
    """Queries over payments."""

    def for_user(self, user: models.Model) -> "PaymentQuerySet":
        """Restrict to one customer's payments."""
        return self.filter(order__user=user)

    def successful(self) -> "PaymentQuerySet":
        """Restrict to payments whose money has settled."""
        from apps.payments.models import PaymentState

        return self.filter(status=PaymentState.CAPTURED)

    def pending(self) -> "PaymentQuerySet":
        """Restrict to payments still awaiting an outcome."""
        from apps.payments.models import PaymentState

        return self.filter(status__in=(PaymentState.CREATED, PaymentState.AUTHORISED))

    def failed(self) -> "PaymentQuerySet":
        """Restrict to payments that did not go through."""
        from apps.payments.models import PaymentState

        return self.filter(status=PaymentState.FAILED)

    def refundable(self) -> "PaymentQuerySet":
        """Restrict to captured payments with money still to give back."""
        return self.successful().filter(refunded_amount__lt=models.F("amount"))

    def stale(self, minutes: int = 30) -> "PaymentQuerySet":
        """Payments created but never completed, for the reconciliation sweep.

        A customer who closes the tab mid-checkout leaves one of these behind.
        They hold no stock — the order does — but they need reconciling against
        the gateway before anyone trusts the revenue numbers.
        """
        from apps.payments.models import PaymentState

        cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
        return self.filter(status=PaymentState.CREATED, created_at__lt=cutoff)

    def with_detail(self) -> "PaymentQuerySet":
        """Prefetch attempts and refunds."""
        from apps.payments.models import PaymentAttempt, Refund

        return self.select_related("order").prefetch_related(
            Prefetch(
                "attempts", queryset=PaymentAttempt.objects.order_by("attempt_number")
            ),
            Prefetch("refunds", queryset=Refund.objects.order_by("-created_at")),
        )

    def total_captured(self) -> models.QuerySet:
        """Aggregate settled revenue, for the finance dashboard."""
        return self.successful().aggregate(
            total=Sum("amount"), refunded=Sum("refunded_amount"), count=Count("id")
        )


class RefundQuerySet(models.QuerySet):
    """Queries over refunds."""

    def for_user(self, user: models.Model) -> "RefundQuerySet":
        """Restrict to one customer's refunds."""
        return self.filter(payment__order__user=user)

    def pending(self) -> "RefundQuerySet":
        """Restrict to refunds the gateway has not settled yet."""
        from apps.payments.models import RefundState

        return self.filter(status__in=(RefundState.PENDING, RefundState.PROCESSING))

    def completed(self) -> "RefundQuerySet":
        """Restrict to refunds the customer has received."""
        from apps.payments.models import RefundState

        return self.filter(status=RefundState.PROCESSED)

    def with_order(self) -> "RefundQuerySet":
        """Join the payment and its order."""
        return self.select_related("payment", "payment__order")


class WebhookLogQuerySet(models.QuerySet):
    """Queries over received webhooks."""

    def unprocessed(self) -> "WebhookLogQuerySet":
        """Webhooks received but not yet acted on."""
        return self.filter(processed_at__isnull=True)

    def failed(self) -> "WebhookLogQuerySet":
        """Webhooks whose processing raised.

        The queue an operator works through after an incident: each one is a
        payment event the system received and could not apply.
        """
        return self.exclude(error="")

    def duplicates(self) -> "WebhookLogQuerySet":
        """Webhooks the provider re-sent after we had already handled them."""
        return self.filter(is_duplicate=True)


PaymentManager = models.Manager.from_queryset(PaymentQuerySet)
RefundManager = models.Manager.from_queryset(RefundQuerySet)
WebhookLogManager = models.Manager.from_queryset(WebhookLogQuerySet)
