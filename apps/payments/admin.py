"""Django admin for the payments module.

Everything here is read-mostly. A payment row is a record of money that moved;
editing one to make the books balance is how a reconciliation problem becomes a
fraud investigation. Refunds are issued through the service layer, which calls
the gateway — never by typing a number into a form.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.payments.models import (
    Payment,
    PaymentAttempt,
    PaymentState,
    PaymentWebhookLog,
    Refund,
    RefundState,
)

STATUS_COLOURS: dict[str, str] = {
    PaymentState.CREATED: "#b45309",
    PaymentState.AUTHORISED: "#1d4ed8",
    PaymentState.CAPTURED: "#15803d",
    PaymentState.FAILED: "#b91c1c",
    PaymentState.CANCELLED: "#6b7280",
    PaymentState.REFUNDED: "#6b7280",
    PaymentState.PARTIALLY_REFUNDED: "#7c3aed",
}


class PaymentAttemptInline(admin.TabularInline):
    """Attempt history, read-only."""

    model = PaymentAttempt
    extra = 0
    can_delete = False
    fields = ("attempt_number", "status", "failure_reason", "retry_count", "created_at")
    readonly_fields = fields
    ordering = ("attempt_number",)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Attempts are written by the service layer."""
        return False


class RefundInline(admin.TabularInline):
    """Refunds against a payment, read-only."""

    model = Refund
    extra = 0
    can_delete = False
    fields = ("amount", "status", "reason", "gateway_refund_id", "processed_at")
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Refunds are issued through the API, which calls the gateway."""
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Admin for payments."""

    list_display = (
        "identifier",
        "order_link",
        "gateway",
        "method",
        "amount_display",
        "status_pill",
        "refunded_amount",
        "created_at",
    )
    list_display_links = ("identifier",)
    list_filter = ("status", "gateway", "method", "created_at")
    search_fields = (
        "gateway_payment_id",
        "gateway_order_id",
        "transaction_id",
        "reference_number",
        "order__order_number",
        "order__user__email",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("order", "order__user")
    inlines = [PaymentAttemptInline, RefundInline]
    list_per_page = 50

    # Every field is frozen. A payment is a record of what a gateway did; the
    # only legitimate way to change the picture is another gateway call.
    readonly_fields = (
        "uuid",
        "order",
        "gateway",
        "method",
        "gateway_order_id",
        "gateway_payment_id",
        "gateway_signature",
        "transaction_id",
        "reference_number",
        "amount",
        "refunded_amount",
        "currency",
        "status",
        "failure_reason",
        "captured_at",
        "raw_response",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Payments are created by checkout, never by hand."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Payment records are permanent."""
        return False

    @admin.display(description=_("Payment"))
    def identifier(self, obj: Payment) -> str:
        """Column showing the gateway identifier."""
        return obj.gateway_payment_id or obj.gateway_order_id or str(obj.uuid)[:8]

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_link(self, obj: Payment) -> str:
        """Link through to the order."""
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)

    @admin.display(description=_("Amount"), ordering="amount")
    def amount_display(self, obj: Payment) -> str:
        """Column showing the amount and anything refunded from it."""
        if obj.refunded_amount:
            return format_html(
                "{} {}<br/><span style='color:#7c3aed;font-size:11px;'>-{} refunded</span>",
                obj.currency,
                obj.amount,
                obj.refunded_amount,
            )
        return f"{obj.currency} {obj.amount}"

    @admin.display(description=_("Status"), ordering="status")
    def status_pill(self, obj: Payment) -> str:
        """Colour-coded status."""
        colour = STATUS_COLOURS.get(obj.status, "#374151")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            colour,
            obj.get_status_display(),
        )


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    """Admin for refunds."""

    list_display = (
        "gateway_refund_id",
        "order_link",
        "amount_display",
        "status_pill",
        "reason",
        "processed_at",
        "created_at",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = (
        "gateway_refund_id",
        "reference_number",
        "payment__gateway_payment_id",
        "payment__order__order_number",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("payment", "payment__order")
    actions = ["mark_processed"]

    readonly_fields = (
        "uuid",
        "payment",
        "amount",
        "currency",
        "reason",
        "gateway_refund_id",
        "raw_response",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Refunds are issued through the API so the gateway is actually called.

        A refund typed into the admin would mark the customer refunded while
        their money stayed exactly where it was.
        """
        return False

    @admin.display(description=_("Order"), ordering="payment__order__order_number")
    def order_link(self, obj: Refund) -> str:
        """Link through to the order."""
        order = obj.payment.order
        url = reverse("admin:orders_order_change", args=[order.pk])
        return format_html('<a href="{}">{}</a>', url, order.order_number)

    @admin.display(description=_("Amount"), ordering="amount")
    def amount_display(self, obj: Refund) -> str:
        """Column showing the refund and whether it is partial."""
        suffix = " (partial)" if obj.is_partial else ""
        return f"{obj.currency} {obj.amount}{suffix}"

    @admin.display(description=_("Status"), ordering="status")
    def status_pill(self, obj: Refund) -> str:
        """Colour-coded status."""
        colours = {
            RefundState.PENDING: "#b45309",
            RefundState.PROCESSING: "#1d4ed8",
            RefundState.PROCESSED: "#15803d",
            RefundState.FAILED: "#b91c1c",
        }
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            colours.get(obj.status, "#374151"),
            obj.get_status_display(),
        )

    @admin.action(description=_("Mark as processed (reconciliation only)"))
    def mark_processed(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Close out refunds confirmed settled from the gateway's report.

        For reconciliation after a webhook was missed — it records that money
        arrived, it does not send any.
        """
        from django.utils import timezone

        updated = queryset.exclude(status=RefundState.PROCESSED).update(
            status=RefundState.PROCESSED, processed_at=timezone.now()
        )
        self.message_user(
            request,
            _("%(count)d refund(s) marked processed.") % {"count": updated},
            messages.SUCCESS,
        )


@admin.register(PaymentWebhookLog)
class PaymentWebhookLogAdmin(admin.ModelAdmin):
    """Read-only audit of every webhook received."""

    list_display = (
        "created_at",
        "gateway",
        "event_type",
        "event_id",
        "state",
        "payment_link",
    )
    list_filter = ("gateway", "event_type", "is_duplicate", "is_verified", "created_at")
    search_fields = ("event_id", "event_type", "payment__gateway_payment_id")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("payment",)
    list_per_page = 100

    readonly_fields = tuple(
        field.name for field in PaymentWebhookLog._meta.fields
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Webhook logs are written by the receiver."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """An audit trail somebody can edit answers nothing."""
        return False

    @admin.display(description=_("State"))
    def state(self, obj: PaymentWebhookLog) -> str:
        """Column flagging duplicates and failures — the two worth looking at."""
        if obj.error:
            return format_html('<b style="color:#b91c1c;">error</b>')
        if obj.is_duplicate:
            return format_html('<span style="color:#6b7280;">duplicate</span>')
        if obj.is_processed:
            return format_html('<span style="color:#15803d;">processed</span>')
        return format_html('<span style="color:#b45309;">pending</span>')

    @admin.display(description=_("Payment"))
    def payment_link(self, obj: PaymentWebhookLog) -> str:
        """Link through to the payment, when the event matched one."""
        if not obj.payment_id:
            return "—"
        url = reverse("admin:payments_payment_change", args=[obj.payment_id])
        return format_html('<a href="{}">{}</a>', url, obj.payment.gateway_payment_id or obj.payment_id)
