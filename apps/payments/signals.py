"""Signal receivers for the payments module.

Logging and reconciliation only. Every state change that matters is written
explicitly by :mod:`apps.payments.services`, inside a transaction, because
money must not move as a side effect of something else being saved.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.logging import get_logger
from apps.payments.models import Payment, PaymentState, Refund, RefundState

logger = get_logger(__name__)


@receiver(post_save, sender=Payment, dispatch_uid="payments.log_payment")
def log_payment(sender: type, instance: Payment, created: bool, **kwargs: Any) -> None:
    """Record every payment state change at INFO, for revenue reconciliation.

    The finance team reconciles the gateway's settlement report against these
    lines, so they carry the identifiers both sides can join on.
    """
    logger.info(
        "payment %s id=%s order=%s gateway=%s status=%s amount=%s %s",
        "created" if created else "updated",
        instance.gateway_payment_id or instance.gateway_order_id,
        instance.order_id,
        instance.gateway,
        instance.status,
        instance.amount,
        instance.currency,
    )


@receiver(post_save, sender=Payment, dispatch_uid="payments.alert_on_failure")
def alert_on_failure(sender: type, instance: Payment, **kwargs: Any) -> None:
    """Raise the log level when a payment fails.

    Split from the INFO line so a failure-rate alert can key on ERROR without
    parsing message text — a spike here is the first sign of a gateway
    outage or a misconfigured key.
    """
    if instance.status != PaymentState.FAILED:
        return

    logger.error(
        "payment failed order=%s gateway=%s reason=%s",
        instance.order_id,
        instance.gateway,
        instance.failure_reason,
    )


@receiver(post_save, sender=Refund, dispatch_uid="payments.log_refund")
def log_refund(sender: type, instance: Refund, created: bool, **kwargs: Any) -> None:
    """Record refunds, escalating failures.

    A failed refund is worse than a failed payment: the customer is out of
    pocket and waiting, and nothing retries automatically.
    """
    if instance.status == RefundState.FAILED:
        logger.error(
            "refund FAILED payment=%s amount=%s reason=%s",
            instance.payment_id,
            instance.amount,
            instance.notes,
        )
        return

    logger.info(
        "refund %s id=%s payment=%s amount=%s status=%s",
        "created" if created else "updated",
        instance.gateway_refund_id,
        instance.payment_id,
        instance.amount,
        instance.status,
    )
