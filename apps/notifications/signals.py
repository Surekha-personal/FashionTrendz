"""Notification triggers.

Every automatic notification in the system is wired from here. Deliberately
concentrated in one file rather than sprinkled through the modules that produce
the events, for two reasons.

First, it means Modules 2–9 needed no edits: this app reaches into their
signals rather than them reaching out to this one, so the dependency arrow
points one way and the completed modules stay closed.

Second, "which events do we email about?" is a question with one answer, and
that answer is this file. Scattering the triggers would make it a grep.

Delivery failures never propagate. A notification is a side effect of something
that already happened, and losing an order because a mail server was down would
be a far worse bug than a missing email — :func:`services.notify` swallows
delivery errors, and the receivers here guard the lookups around it.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.choices import OrderStatus
from apps.notifications import services

logger = logging.getLogger(__name__)

#: Order states that produce a customer-facing message, mapped to their event.
#: A state absent from this map is an internal transition the customer does not
#: need to hear about — PROCESSING is warehouse vocabulary, not news.
ORDER_STATUS_EVENTS: dict[str, str] = {
    OrderStatus.PACKED: "order_packed",
    OrderStatus.SHIPPED: "order_shipped",
    OrderStatus.OUT_FOR_DELIVERY: "order_out_for_delivery",
    OrderStatus.DELIVERED: "order_delivered",
    OrderStatus.CANCELLED: "order_cancelled",
}


def _order_context(order: Any) -> dict[str, Any]:
    """Return the context every order template reads."""
    return {
        "order_number": order.order_number,
        "total": order.grand_total,
        "currency": order.currency,
        "reason": getattr(order, "cancel_reason", "") or "",
    }


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


@receiver(post_save, dispatch_uid="notifications_welcome_email")
def send_welcome(sender: type, instance: Any, created: bool, **kwargs: Any) -> None:
    """Welcome a newly registered customer.

    Connected without a ``sender`` and filtered by model name, so this module
    does not import the users app at startup — which would make the import
    order between two apps that both load signals in ``ready()`` matter.

    Staff accounts are skipped: a superuser created by ``createsuperuser`` is
    not a shopper and does not need onboarding copy.
    """
    if sender.__name__ != "User" or not created:
        return
    if getattr(instance, "is_staff", False) or getattr(instance, "is_superuser", False):
        return

    services.notify(instance, "welcome", {})


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


@receiver(post_save, dispatch_uid="notifications_order_events")
def send_order_notifications(
    sender: type, instance: Any, created: bool, **kwargs: Any
) -> None:
    """Announce order placement and every customer-visible status change.

    Two models feed this. ``Order`` on creation gives "order placed";
    ``OrderStatusHistory`` on creation gives every subsequent transition.

    Reading the history row rather than watching ``Order.status`` is what makes
    this exactly-once. A ``post_save`` on ``Order`` fires for any field change —
    an invoice number, a payment reference — and would re-announce "shipped"
    each time. A history row is written once per real transition.
    """
    if not created:
        return

    name = sender.__name__

    if name == "Order":
        services.notify(instance.user, "order_placed", _order_context(instance))
        return

    if name != "OrderStatusHistory":
        return

    event = ORDER_STATUS_EVENTS.get(instance.status)
    if not event:
        return

    order = instance.order
    context = _order_context(order)
    context["reason"] = instance.remarks or context["reason"]

    if event == "order_shipped":
        shipment = order.shipments.order_by("-id").first()
        context.update(
            courier=getattr(shipment, "courier_name", "") or "our courier partner",
            tracking_number=getattr(shipment, "tracking_number", "") or "",
        )

    services.notify(order.user, event, context)


# ---------------------------------------------------------------------------
# Payments and refunds
# ---------------------------------------------------------------------------


@receiver(post_save, dispatch_uid="notifications_payment_events")
def send_payment_notifications(sender: type, instance: Any, **kwargs: Any) -> None:
    """Announce a captured or failed payment, and refund progress.

    Fires on every save rather than only on creation — a payment is *created*
    as ``created`` and only becomes captured later, so creation is the one
    moment there is nothing to say. Repeat announcements are prevented by
    :func:`_already_sent`, not by the signal's ``created`` flag.
    """
    name = sender.__name__

    if name == "Payment":
        _handle_payment(instance)
    elif name == "Refund":
        _handle_refund(instance)


def _handle_payment(payment: Any) -> None:
    """Send the success or failure message for one payment."""
    from apps.payments.models import PaymentState

    event = {
        PaymentState.CAPTURED: "payment_success",
        PaymentState.FAILED: "payment_failed",
    }.get(payment.status)
    if not event:
        return

    order = payment.order
    if _already_sent(order.user_id, event, order.order_number):
        return

    services.notify(
        order.user,
        event,
        {
            "order_number": order.order_number,
            "amount": payment.amount,
            "currency": payment.currency,
            "reference": payment.gateway_payment_id or "",
            "reason": payment.failure_reason
            or "Your bank did not authorise the payment.",
        },
    )


def _handle_refund(refund: Any) -> None:
    """Send the initiated or completed message for one refund."""
    from apps.payments.models import RefundState

    event = {
        RefundState.PENDING: "refund_initiated",
        RefundState.PROCESSED: "refund_completed",
    }.get(refund.status)
    if not event:
        return

    order = refund.payment.order
    if _already_sent(order.user_id, event, order.order_number):
        return

    services.notify(
        order.user,
        event,
        {
            "order_number": order.order_number,
            "amount": refund.amount,
            "currency": refund.currency,
            "reference": refund.reference_number or refund.gateway_refund_id or "",
        },
    )


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------


@receiver(post_save, dispatch_uid="notifications_review_moderated")
def send_review_outcome(sender: type, instance: Any, created: bool, **kwargs: Any) -> None:
    """Tell an author when their review is published or turned down."""
    if sender.__name__ != "Review" or created or not instance.moderated_at:
        return

    from apps.reviews.models import ModerationStatus

    event = {
        ModerationStatus.APPROVED: "review_approved",
        ModerationStatus.REJECTED: "review_rejected",
    }.get(instance.status)
    if not event:
        return

    services.notify(
        instance.user,
        event,
        {
            "product_name": instance.product.name,
            "product_slug": instance.product.slug,
            "reason": instance.rejection_reason or "",
        },
    )


# ---------------------------------------------------------------------------
# Duplicate suppression
# ---------------------------------------------------------------------------


def _already_sent(user_id: int, event: str, order_number: str) -> bool:
    """Return whether this exact message has already gone out.

    Payment and refund rows are saved several times as a gateway call
    progresses, and a webhook can arrive twice. Without this guard a customer
    gets "payment received" once per save.

    Matched on the rendered subject, which carries the order number, rather
    than on a dedicated table: the ledger already records every message sent,
    and a second table tracking what the first table tracks would be one more
    thing to keep consistent.
    """
    from apps.notifications.models import Notification

    return (
        Notification.objects.filter(user_id=user_id, event=event)
        .filter(subject__contains=order_number)
        .exists()
    )
