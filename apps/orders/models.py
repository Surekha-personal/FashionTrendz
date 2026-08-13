"""Order models.

Four models: :class:`Order`, its :class:`OrderItem` lines, an append-only
:class:`OrderStatusHistory` and one :class:`Shipment` per parcel.

**Everything an order shows is a snapshot.** Addresses are stored as JSON, not
as a foreign key; line items carry their own name, SKU, size, colour and money
rather than reading them from the product. That is deliberate and it is the
single most important decision in this module: a customer must be able to open
a two-year-old invoice and see what they actually bought at the price they
actually paid, after the product was renamed, repriced, or deleted outright.
A live join would rewrite history every time a merchandiser edits the catalogue.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.choices import (
    CANCELLABLE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    Currency,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from apps.core.constants import DEFAULT_CURRENCY, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS
from apps.core.mixins import BaseModel
from apps.orders.managers import OrderItemManager, OrderManager, ShipmentManager
from apps.orders.validators import (
    invoice_number_validator,
    order_number_validator,
    tracking_number_validator,
    validate_address_snapshot,
)
from apps.products.models import Product, ProductVariant


class DeliveryStatus(models.TextChoices):
    """Where the parcel is, as distinct from where the order is.

    Two fields rather than one because they answer different questions and move
    on different clocks: an order can be CANCELLED while its parcel is already
    IN_TRANSIT, and a delivery can FAIL twice before the order status changes at
    all. Collapsing them loses the second attempt.
    """

    NOT_DISPATCHED = "not_dispatched", _("Not dispatched")
    DISPATCHED = "dispatched", _("Dispatched")
    IN_TRANSIT = "in_transit", _("In transit")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for delivery")
    DELIVERED = "delivered", _("Delivered")
    FAILED = "failed", _("Delivery failed")
    RETURNED_TO_ORIGIN = "rto", _("Returned to origin")


class DeliveryMethod(models.TextChoices):
    """Shipping speed the customer chose at checkout."""

    STANDARD = "standard", _("Standard delivery")
    EXPRESS = "express", _("Express delivery")
    SCHEDULED = "scheduled", _("Scheduled delivery")


class Order(BaseModel):
    """A placed order: what was bought, for how much, and where it is going."""

    order_number = models.CharField(
        _("order number"),
        max_length=32,
        unique=True,
        db_index=True,
        validators=[order_number_validator],
    )
    invoice_number = models.CharField(
        _("invoice number"),
        max_length=32,
        blank=True,
        db_index=True,
        validators=[invoice_number_validator],
        help_text=_("Assigned when the invoice is first generated."),
    )
    invoice_file = models.FileField(
        _("invoice PDF"),
        upload_to="invoices/%Y/%m/",
        blank=True,
        null=True,
    )

    # PROTECT, not CASCADE: deleting a customer must not silently erase the
    # sales history the finance team reconciles against. Anonymise the account
    # instead — the order rows outlive it.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name=_("customer"),
    )

    # -- Address snapshots --------------------------------------------------

    shipping_address = models.JSONField(
        _("shipping address"),
        validators=[validate_address_snapshot],
        help_text=_("Frozen copy of the delivery address as it was at checkout."),
    )
    billing_address = models.JSONField(
        _("billing address"),
        validators=[validate_address_snapshot],
        help_text=_("Frozen copy of the billing address as it was at checkout."),
    )

    # -- Money --------------------------------------------------------------
    # Copied from the cart's line snapshots, never recomputed. The customer
    # agreed to these numbers; re-deriving them at any later point risks
    # charging something they never saw.

    subtotal = models.DecimalField(
        _("subtotal"), max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    discount = models.DecimalField(
        _("discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    coupon_code = models.CharField(_("coupon code"), max_length=40, blank=True)
    coupon_discount = models.DecimalField(
        _("coupon discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    shipping_charge = models.DecimalField(
        _("shipping charge"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    platform_fee = models.DecimalField(
        _("platform fee"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    tax = models.DecimalField(
        _("GST"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    grand_total = models.DecimalField(
        _("grand total"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
    )
    currency = models.CharField(
        _("currency"), max_length=3, choices=Currency.choices, default=DEFAULT_CURRENCY
    )

    # -- Payment ------------------------------------------------------------

    payment_method = models.CharField(
        _("payment method"),
        max_length=16,
        choices=PaymentMethod.choices,
        default=PaymentMethod.COD,
    )
    payment_status = models.CharField(
        _("payment status"),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )
    payment_reference = models.CharField(
        _("payment reference"),
        max_length=100,
        blank=True,
        help_text=_("Gateway transaction id. Populated by the payments module."),
    )

    # -- Fulfilment ---------------------------------------------------------

    status = models.CharField(
        _("order status"),
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    delivery_status = models.CharField(
        _("delivery status"),
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.NOT_DISPATCHED,
        db_index=True,
    )
    delivery_method = models.CharField(
        _("delivery method"),
        max_length=16,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.STANDARD,
    )

    estimated_delivery_date = models.DateField(
        _("estimated delivery"), null=True, blank=True
    )
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)
    cancel_reason = models.CharField(_("cancel reason"), max_length=255, blank=True)

    notes = models.TextField(
        _("notes"), blank=True, help_text=_("Delivery instructions from the customer.")
    )
    internal_notes = models.TextField(
        _("internal notes"), blank=True, help_text=_("Staff-only. Never shown to the customer.")
    )

    # -- Inventory bookkeeping ----------------------------------------------

    stock_committed = models.BooleanField(
        _("stock committed"),
        default=False,
        editable=False,
        help_text=_(
            "True once on-hand stock has been decremented. Decides whether a "
            "cancellation releases a reservation or puts units back on the shelf."
        ),
    )

    objects = OrderManager()

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="order_user_recent_idx"),
            models.Index(fields=["status", "-created_at"], name="order_status_idx"),
            models.Index(
                fields=["payment_status", "-created_at"], name="order_payment_idx"
            ),
            models.Index(
                fields=["delivery_status", "-created_at"], name="order_delivery_idx"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(grand_total__gte=Decimal("0")),
                name="order_grand_total_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=Decimal("0")),
                name="order_subtotal_not_negative",
            ),
        ]

    def __str__(self) -> str:
        return self.order_number

    # -- Derived state ------------------------------------------------------

    @property
    def line_count(self) -> int:
        """Return the number of distinct lines."""
        annotated = getattr(self, "_line_count", None)
        if annotated is not None:
            return annotated
        return self.items.count()

    @property
    def unit_count(self) -> int:
        """Return the total units ordered."""
        annotated = getattr(self, "_unit_count", None)
        if annotated is not None:
            return annotated or 0
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def is_cancellable(self) -> bool:
        """Return whether the customer may still cancel this order themselves."""
        return self.status in CANCELLABLE_ORDER_STATUSES

    @property
    def is_terminal(self) -> bool:
        """Return whether this order can still change state."""
        return self.status in TERMINAL_ORDER_STATUSES

    @property
    def is_paid(self) -> bool:
        """Return whether the money has settled."""
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_cod(self) -> bool:
        """Return whether this is a cash-on-delivery order."""
        return self.payment_method == PaymentMethod.COD

    @property
    def total_savings(self) -> Decimal:
        """Return what the customer saved against MRP, including any coupon."""
        return self.discount + self.coupon_discount

    @property
    def shipping_name(self) -> str:
        """Return the recipient's name from the shipping snapshot."""
        return str(self.shipping_address.get("full_name", ""))

    def latest_shipment(self) -> "Shipment | None":
        """Return the most recent parcel, if any."""
        prefetched = getattr(self, "_prefetched_objects_cache", {}).get("shipments")
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return self.shipments.order_by("-created_at").first()


class OrderItem(BaseModel):
    """One purchased line, frozen at the moment of purchase.

    The product and variant foreign keys exist only so "buy it again" can find
    the live row. Nothing rendered on an invoice reads through them — every
    displayed value is a column on this table.
    """

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name=_("order")
    )

    # SET_NULL, not CASCADE: deleting a product must never delete the record
    # that someone bought it. The snapshot columns keep the line renderable.
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True,
        blank=True,
        verbose_name=_("product"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True,
        blank=True,
        verbose_name=_("variant"),
    )

    # -- Snapshot -----------------------------------------------------------

    product_name = models.CharField(_("product name"), max_length=200)
    product_slug = models.SlugField(_("product slug"), max_length=255, blank=True)
    brand_name = models.CharField(_("brand"), max_length=120, blank=True)
    sku = models.CharField(_("SKU"), max_length=50)
    size = models.CharField(_("size"), max_length=16, blank=True)
    color = models.CharField(_("colour"), max_length=40, blank=True)
    image_url = models.CharField(_("image URL"), max_length=500, blank=True)

    # -- Money --------------------------------------------------------------

    mrp = models.DecimalField(
        _("MRP"), max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    selling_price = models.DecimalField(
        _("selling price"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
    )
    discount = models.DecimalField(
        _("discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    tax = models.DecimalField(
        _("tax"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    quantity = models.PositiveSmallIntegerField(_("quantity"))
    subtotal = models.DecimalField(
        _("subtotal"), max_digits=PRICE_MAX_DIGITS, decimal_places=PRICE_DECIMAL_PLACES
    )
    grand_total = models.DecimalField(
        _("line total"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
    )

    objects = OrderItemManager()

    class Meta:
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1), name="orderitem_quantity_positive"
            ),
        ]
        indexes = [
            models.Index(fields=["order"], name="orderitem_order_idx"),
            models.Index(fields=["sku"], name="orderitem_sku_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.product_name} ({self.sku})"

    @property
    def display_variant(self) -> str:
        """Return the colour/size label shown on the invoice."""
        parts = [part for part in (self.color, self.size) if part]
        return " / ".join(parts)

    @property
    def can_reorder(self) -> bool:
        """Return whether this line's variant can still be bought."""
        return bool(
            self.variant_id
            and self.variant
            and self.variant.is_active
            and self.variant.available_stock > 0
            and self.product
            and self.product.is_visible
        )


class OrderStatusHistory(BaseModel):
    """One entry in an order's timeline.

    Append-only by convention: rows are written, never edited or deleted. The
    timeline is what a support agent reads to answer "why did this happen", and
    a rewritable audit log answers nothing.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name=_("order"),
    )
    previous_status = models.CharField(
        _("previous status"), max_length=20, choices=OrderStatus.choices, blank=True
    )
    status = models.CharField(
        _("status"), max_length=20, choices=OrderStatus.choices
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="order_status_changes",
        null=True,
        blank=True,
        verbose_name=_("changed by"),
        help_text=_("Null for automated transitions."),
    )
    remarks = models.CharField(_("remarks"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("order status history")
        verbose_name_plural = _("order status history")
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["order", "created_at"], name="statushistory_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.order.order_number}: {self.previous_status or '-'} to {self.status}"


class Shipment(BaseModel):
    """One parcel dispatched against an order.

    Separate from the order so a split shipment — two parcels from two
    warehouses — is representable without inventing a second order.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="shipments",
        verbose_name=_("order"),
    )
    courier_name = models.CharField(_("courier"), max_length=100)
    tracking_number = models.CharField(
        _("tracking number"),
        max_length=64,
        blank=True,
        db_index=True,
        validators=[tracking_number_validator],
    )
    tracking_url = models.URLField(_("tracking URL"), max_length=500, blank=True)

    dispatched_at = models.DateTimeField(_("dispatched at"), null=True, blank=True)
    expected_delivery_date = models.DateField(
        _("expected delivery"), null=True, blank=True
    )
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)

    remarks = models.CharField(_("remarks"), max_length=255, blank=True)

    objects = ShipmentManager()

    class Meta:
        verbose_name = _("shipment")
        verbose_name_plural = _("shipments")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"], name="shipment_order_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.courier_name} {self.tracking_number or '(no tracking)'}"

    @property
    def is_delivered(self) -> bool:
        """Return whether this parcel has arrived."""
        return self.delivered_at is not None

    @property
    def is_in_transit(self) -> bool:
        """Return whether this parcel is with the courier."""
        return self.dispatched_at is not None and self.delivered_at is None

    @property
    def is_overdue(self) -> bool:
        """Return whether the promised date has passed without delivery."""
        return bool(
            self.expected_delivery_date
            and not self.delivered_at
            and self.expected_delivery_date < timezone.localdate()
        )
