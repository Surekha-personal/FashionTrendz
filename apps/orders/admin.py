"""Django admin for the orders module.

Built for the two people who use it most: a support agent answering "where is
my order", and a warehouse operator moving parcels through fulfilment.
"""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _

from apps.core.choices import OrderStatus
from apps.orders.models import Order, OrderItem, OrderStatusHistory, Shipment
from apps.orders.services import transition_order

#: Colours for the status pill in the list view.
STATUS_COLOURS: dict[str, str] = {
    OrderStatus.PENDING: "#b45309",
    OrderStatus.CONFIRMED: "#1d4ed8",
    OrderStatus.PROCESSING: "#1d4ed8",
    OrderStatus.PACKED: "#7c3aed",
    OrderStatus.SHIPPED: "#0f766e",
    OrderStatus.OUT_FOR_DELIVERY: "#0f766e",
    OrderStatus.DELIVERED: "#15803d",
    OrderStatus.CANCELLED: "#b91c1c",
    OrderStatus.RETURNED: "#b91c1c",
    OrderStatus.REFUNDED: "#6b7280",
}


class OrderItemInline(admin.TabularInline):
    """Purchased lines, shown read-only.

    Order lines are a historical record. Editing one after the fact would make
    the invoice disagree with what was charged, so the whole inline is frozen —
    a correction is a return or a credit note, never a quiet edit.
    """

    model = OrderItem
    extra = 0
    can_delete = False
    fields = (
        "product_name",
        "sku",
        "display_variant",
        "quantity",
        "mrp",
        "selling_price",
        "grand_total",
    )
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Order lines are never added by hand."""
        return False

    @admin.display(description=_("Variant"))
    def display_variant(self, obj: OrderItem) -> str:
        """Column showing colour and size."""
        return obj.display_variant or "—"


class OrderStatusHistoryInline(admin.TabularInline):
    """The order timeline, read-only.

    Append-only by design: an audit trail somebody can edit answers nothing.
    """

    model = OrderStatusHistory
    extra = 0
    can_delete = False
    fields = ("created_at", "previous_status", "status", "changed_by", "remarks")
    readonly_fields = fields
    ordering = ("created_at",)

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Entries are written by the service layer, never by hand."""
        return False


class ShipmentInline(admin.TabularInline):
    """Parcels dispatched against the order."""

    model = Shipment
    extra = 0
    fields = (
        "courier_name",
        "tracking_number",
        "tracking_url",
        "dispatched_at",
        "expected_delivery_date",
        "delivered_at",
    )
    ordering = ("-created_at",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin for orders."""

    list_display = (
        "order_number",
        "customer",
        "status_pill",
        "payment_summary",
        "unit_total",
        "grand_total_display",
        "estimated_delivery_date",
        "created_at",
    )
    list_display_links = ("order_number",)
    list_filter = (
        "status",
        "payment_status",
        "payment_method",
        "delivery_status",
        "delivery_method",
        "created_at",
    )
    search_fields = (
        "order_number",
        "invoice_number",
        "user__email",
        "user__first_name",
        "user__last_name",
        "items__sku",
        "items__product_name",
        "shipments__tracking_number",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    inlines = [OrderItemInline, ShipmentInline, OrderStatusHistoryInline]

    actions = [
        "mark_confirmed",
        "mark_processing",
        "mark_packed",
        "mark_shipped",
        "mark_out_for_delivery",
        "mark_delivered",
        "generate_invoices",
    ]

    # Money and identifiers are frozen. Changing a total after the fact makes
    # the order disagree with what the customer was charged, and the status
    # field is writable only through the state machine, not by typing.
    readonly_fields = (
        "uuid",
        "order_number",
        "invoice_number",
        "invoice_file",
        "user",
        "shipping_address",
        "billing_address",
        "subtotal",
        "discount",
        "coupon_code",
        "coupon_discount",
        "shipping_charge",
        "platform_fee",
        "tax",
        "grand_total",
        "currency",
        "stock_committed",
        "delivered_at",
        "cancelled_at",
        "created_at",
        "updated_at",
        "address_block",
    )

    fieldsets = (
        (None, {"fields": ("order_number", "user", "status", "created_at")}),
        (
            _("Fulfilment"),
            {
                "fields": (
                    "delivery_status",
                    "delivery_method",
                    "estimated_delivery_date",
                    "delivered_at",
                )
            },
        ),
        (
            _("Payment"),
            {"fields": ("payment_method", "payment_status", "payment_reference")},
        ),
        (_("Addresses"), {"fields": ("address_block",)}),
        (
            _("Money"),
            {
                "fields": (
                    "subtotal",
                    ("discount", "coupon_code", "coupon_discount"),
                    ("shipping_charge", "platform_fee", "tax"),
                    "grand_total",
                    "currency",
                )
            },
        ),
        (_("Invoice"), {"fields": ("invoice_number", "invoice_file")}),
        (
            _("Cancellation"),
            {"fields": ("cancelled_at", "cancel_reason"), "classes": ("collapse",)},
        ),
        (_("Notes"), {"fields": ("notes", "internal_notes")}),
        (
            _("Audit"),
            {"fields": ("uuid", "stock_committed", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join and annotate so the list view issues no per-row query."""
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .annotate(
                _line_count=Count("items", distinct=True),
                _unit_count=Sum("items__quantity"),
            )
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Orders are created by checkout, never by hand.

        A hand-made order would have no stock movement, no cart to reconcile
        against and no payment record — three silent inconsistencies.
        """
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Orders are never deleted. Cancel them instead."""
        return False

    # -- Columns ------------------------------------------------------------

    @admin.display(description=_("Customer"), ordering="user__email")
    def customer(self, obj: Order) -> str:
        """Column linking to the customer."""
        url = reverse("admin:users_user_change", args=[obj.user_id])
        return format_html('<a href="{}">{}</a>', url, obj.user.email)

    @admin.display(description=_("Status"), ordering="status")
    def status_pill(self, obj: Order) -> str:
        """Colour-coded status, so a queue is scannable at a glance."""
        colour = STATUS_COLOURS.get(obj.status, "#374151")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:11px;">{}</span>',
            colour,
            obj.get_status_display(),
        )

    @admin.display(description=_("Payment"), ordering="payment_status")
    def payment_summary(self, obj: Order) -> str:
        """Column showing method and settlement state together."""
        colour = "#15803d" if obj.is_paid else "#b45309"
        return format_html(
            '{}<br/><span style="color:{};font-size:11px;">{}</span>',
            obj.get_payment_method_display(),
            colour,
            obj.get_payment_status_display(),
        )

    @admin.display(description=_("Units"), ordering="_unit_count")
    def unit_total(self, obj: Order) -> int:
        """Column showing total units ordered."""
        return getattr(obj, "_unit_count", 0) or 0

    @admin.display(description=_("Total"), ordering="grand_total")
    def grand_total_display(self, obj: Order) -> str:
        """Column showing the order value."""
        return f"{obj.currency} {obj.grand_total}"

    @admin.display(description=_("Addresses"))
    def address_block(self, obj: Order) -> str:
        """Render both frozen address snapshots side by side."""
        def block(title: str, address: dict[str, Any]) -> str:
            rows = format_html_join(
                "", "<div>{}</div>", ((v,) for v in address.values() if v)
            )
            return format_html(
                '<div style="display:inline-block;vertical-align:top;'
                'margin-right:32px;"><b>{}</b>{}</div>',
                title,
                rows,
            )

        return format_html(
            "{}{}",
            block(_("Shipping"), obj.shipping_address or {}),
            block(_("Billing"), obj.billing_address or {}),
        )

    # -- Bulk actions -------------------------------------------------------

    def _bulk_transition(
        self, request: HttpRequest, queryset: QuerySet, target: str
    ) -> None:
        """Move each selected order, reporting the ones that could not move.

        Deliberately a loop rather than ``queryset.update()``: every move has to
        go through the state machine so illegal transitions are refused and the
        timeline gets an entry. A bulk UPDATE would skip both.
        """
        moved = 0
        refused: list[str] = []

        for order in queryset:
            try:
                transition_order(
                    order, target, changed_by=request.user, remarks="Bulk update."
                )
                moved += 1
            except Exception as exc:  # BusinessRuleViolation and friends
                refused.append(f"{order.order_number} ({exc})")

        if moved:
            self.message_user(
                request,
                _("%(count)d order(s) moved to %(status)s.")
                % {"count": moved, "status": target},
                messages.SUCCESS,
            )
        if refused:
            self.message_user(
                request,
                _("Could not move: %(orders)s") % {"orders": "; ".join(refused[:10])},
                messages.WARNING,
            )

    @admin.action(description=_("Mark as confirmed"))
    def mark_confirmed(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders to confirmed."""
        self._bulk_transition(request, queryset, OrderStatus.CONFIRMED)

    @admin.action(description=_("Mark as processing"))
    def mark_processing(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders to processing."""
        self._bulk_transition(request, queryset, OrderStatus.PROCESSING)

    @admin.action(description=_("Mark as packed"))
    def mark_packed(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders to packed."""
        self._bulk_transition(request, queryset, OrderStatus.PACKED)

    @admin.action(description=_("Mark as shipped"))
    def mark_shipped(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders to shipped."""
        self._bulk_transition(request, queryset, OrderStatus.SHIPPED)

    @admin.action(description=_("Mark as out for delivery"))
    def mark_out_for_delivery(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders out for delivery."""
        self._bulk_transition(request, queryset, OrderStatus.OUT_FOR_DELIVERY)

    @admin.action(description=_("Mark as delivered"))
    def mark_delivered(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Move selected orders to delivered."""
        self._bulk_transition(request, queryset, OrderStatus.DELIVERED)

    @admin.action(description=_("Generate invoices"))
    def generate_invoices(self, request: HttpRequest, queryset: QuerySet) -> None:
        """Render and store a PDF invoice for each selected order."""
        from apps.orders.services import generate_invoice_pdf

        generated = 0
        for order in queryset:
            generate_invoice_pdf(order)
            generated += 1

        self.message_user(
            request,
            _("%(count)d invoice(s) generated.") % {"count": generated},
            messages.SUCCESS,
        )


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    """Admin for purchased lines, used for product-level sales analysis."""

    list_display = (
        "order_link",
        "product_name",
        "sku",
        "display_variant",
        "quantity",
        "selling_price",
        "grand_total",
    )
    list_filter = ("order__status", "order__created_at")
    search_fields = ("product_name", "sku", "brand_name", "order__order_number")
    ordering = ("-order__created_at",)
    list_select_related = ("order",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Lines are created by checkout only."""
        return False

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the parent order."""
        return super().get_queryset(request).select_related("order", "order__user")

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_link(self, obj: OrderItem) -> str:
        """Link through to the order."""
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)

    @admin.display(description=_("Variant"))
    def display_variant(self, obj: OrderItem) -> str:
        """Column showing colour and size."""
        return obj.display_variant or "—"


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    """Admin for parcels — the operations screen."""

    list_display = (
        "tracking_number",
        "order_link",
        "courier_name",
        "dispatched_at",
        "expected_delivery_date",
        "delivered_at",
        "state",
    )
    list_filter = ("courier_name", "dispatched_at", "delivered_at")
    search_fields = ("tracking_number", "courier_name", "order__order_number")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("order",)
    list_select_related = ("order",)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        """Join the parent order."""
        return super().get_queryset(request).select_related("order")

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_link(self, obj: Shipment) -> str:
        """Link through to the order."""
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)

    @admin.display(description=_("State"))
    def state(self, obj: Shipment) -> str:
        """Column flagging overdue parcels — the ones about to become tickets."""
        if obj.is_delivered:
            return format_html('<span style="color:#15803d;">delivered</span>')
        if obj.is_overdue:
            return format_html('<b style="color:#b91c1c;">overdue</b>')
        if obj.is_in_transit:
            return format_html('<span style="color:#0f766e;">in transit</span>')
        return format_html('<span style="color:#6b7280;">not dispatched</span>')


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    """Read-only audit log of every status change."""

    list_display = ("created_at", "order_link", "previous_status", "status", "changed_by", "remarks")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "remarks")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    list_select_related = ("order", "changed_by")

    def has_add_permission(self, request: HttpRequest) -> bool:
        """Entries are written by the service layer."""
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """An audit trail somebody can edit answers nothing."""
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        """Same reason."""
        return False

    @admin.display(description=_("Order"), ordering="order__order_number")
    def order_link(self, obj: OrderStatusHistory) -> str:
        """Link through to the order."""
        url = reverse("admin:orders_order_change", args=[obj.order_id])
        return format_html('<a href="{}">{}</a>', url, obj.order.order_number)
