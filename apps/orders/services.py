"""Checkout and order business logic.

The whole module exists to make one operation safe: turning a cart into an
order without ever selling stock twice and without ever charging a price the
customer did not see.

Three rules everything here obeys:

* **Money is copied, never recomputed.** The cart's line snapshots are the
  numbers the customer agreed to. Re-deriving them at order time would let a
  catalogue edit between "review" and "place order" change the price silently.
* **Stock moves under a row lock.** Every decrement is a conditional
  ``UPDATE ... WHERE available >= n`` inside ``select_for_update``, so two
  simultaneous checkouts for the last unit cannot both succeed.
* **Status changes go through one function.** :func:`transition_order` is the
  only writer of ``Order.status``, so the state machine and the audit trail
  cannot be bypassed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.cart.models import Cart, CartItem
from apps.cart.services import (
    get_cart_issues,
    get_cart_summary,
    get_or_create_cart,
    recalculate_cart,
)
from apps.core.choices import (
    CANCELLABLE_ORDER_STATUSES,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
)
from apps.core.exceptions import (
    BusinessRuleViolation,
    InsufficientStock,
    ResourceConflict,
)
from apps.core.logging import get_logger
from apps.core.utils import generate_invoice_number, generate_order_number
from apps.orders.models import (
    DeliveryMethod,
    DeliveryStatus,
    Order,
    OrderItem,
    OrderStatusHistory,
    Shipment,
)
from apps.orders.validators import assert_transition, validate_address_snapshot
from apps.products.models import Product, ProductVariant
from apps.users.models import Address

logger = get_logger(__name__)

#: Payment methods a customer may choose today. The placeholders are accepted
#: and recorded, but leave the order awaiting payment rather than confirmed —
#: nothing here contacts a gateway.
SUPPORTED_PAYMENT_METHODS: frozenset[str] = frozenset(PaymentMethod.values)

#: Methods that settle without a gateway round-trip.
OFFLINE_PAYMENT_METHODS: frozenset[str] = frozenset({PaymentMethod.COD})


# ---------------------------------------------------------------------------
# Address snapshots
# ---------------------------------------------------------------------------


def snapshot_address(address: Address) -> dict[str, Any]:
    """Freeze an address into the JSON an order stores.

    A copy rather than a foreign key: a customer who edits their saved address
    next month must not silently rewrite where last month's parcel was sent.
    """
    return {
        # Module 2's Address predates core's UUIDMixin, so it is identified by
        # its integer primary key — which is what that module's serializer
        # already exposes to the frontend.
        "id": address.pk,
        "full_name": address.full_name,
        "mobile": address.mobile,
        "address_line_1": address.address_line_1,
        "address_line_2": address.address_line_2,
        "city": address.city,
        "state": address.state,
        "country": address.country,
        "postal_code": address.postal_code,
    }


def resolve_address(user: Any, address_id: Any) -> Address:
    """Return one of the user's addresses, or raise.

    Scoped to the requesting user, so a caller cannot ship an order to a
    stranger's address by guessing an identifier — the scoping, not the shape
    of the id, is what makes this safe.
    """
    address = Address.objects.filter(user=user, pk=address_id).first()
    if address is None:
        raise BusinessRuleViolation("That delivery address was not found.")
    return address


# ---------------------------------------------------------------------------
# Checkout review
# ---------------------------------------------------------------------------


def get_checkout_context(user: Any) -> dict[str, Any]:
    """Return everything the checkout page needs before an order exists.

    Deliberately read-only: nothing here reserves stock or writes an order, so
    a customer can sit on the checkout page without holding inventory.
    """
    cart = get_or_create_cart(user=user)
    recalculate_cart(cart)

    addresses = list(Address.objects.filter(user=user).order_by("-is_default", "-created_at"))
    default_address = next((a for a in addresses if a.is_default), None)

    return {
        "cart": cart,
        "summary": get_cart_summary(cart),
        "issues": get_cart_issues(cart),
        "addresses": addresses,
        "default_address": default_address,
        "payment_methods": [
            {
                "code": method.value,
                "label": method.label,
                "available": True,
                "is_placeholder": method.value not in OFFLINE_PAYMENT_METHODS,
            }
            for method in PaymentMethod
        ],
        "delivery_methods": [
            {"code": method.value, "label": method.label} for method in DeliveryMethod
        ],
        "is_checkout_ready": bool(addresses) and not get_cart_issues(cart) and not cart.is_empty,
    }


def review_order(
    user: Any,
    *,
    shipping_address_id: Any,
    billing_address_id: Any = None,
    payment_method: str = PaymentMethod.COD,
    delivery_method: str = DeliveryMethod.STANDARD,
) -> dict[str, Any]:
    """Return the exact order that would be created, without creating it.

    The final confirmation screen. Runs every validation ``place_order`` runs,
    so a customer never reaches "Place order" only to be told their bag is
    unbuyable.
    """
    cart = get_or_create_cart(user=user)
    recalculate_cart(cart)

    assert_checkout_ready(cart)
    assert_payment_method(payment_method)

    shipping = resolve_address(user, shipping_address_id)
    billing = (
        resolve_address(user, billing_address_id)
        if billing_address_id
        else shipping
    )

    summary = get_cart_summary(cart)

    return {
        "cart": cart,
        "summary": summary,
        "shipping_address": snapshot_address(shipping),
        "billing_address": snapshot_address(billing),
        "payment_method": payment_method,
        "delivery_method": delivery_method,
        "estimated_delivery_date": estimate_delivery_date(
            summary["estimated_delivery_days"], delivery_method
        ),
        "issues": [],
    }


def assert_checkout_ready(cart: Cart) -> None:
    """Raise unless the cart can become an order right now."""
    if cart.is_empty:
        raise BusinessRuleViolation("Your bag is empty.")

    issues = get_cart_issues(cart)
    if issues:
        names = ", ".join(issue["product"] for issue in issues)
        raise InsufficientStock(
            f"Some items are no longer available: {names}. Please review your bag."
        )


def assert_payment_method(method: str) -> None:
    """Raise unless the payment method is one the platform accepts."""
    if method not in SUPPORTED_PAYMENT_METHODS:
        raise BusinessRuleViolation("That payment method is not available.")


def estimate_delivery_date(days: int, delivery_method: str) -> Any:
    """Return the promised delivery date for a method and lead time.

    Express halves the lead time with a two-day floor, which is the shape of
    every real courier's promise: faster, but not instant.
    """
    lead = max(days or 5, 1)
    if delivery_method == DeliveryMethod.EXPRESS:
        lead = max(lead // 2, 2)
    return timezone.localdate() + timezone.timedelta(days=lead)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def reserve_stock(lines: Iterable[tuple[int, int]]) -> None:
    """Hold ``quantity`` units of each ``variant_id``, or raise.

    Each row is moved with a conditional UPDATE whose WHERE clause re-checks
    availability, so the database decides the winner when two checkouts race
    for the last unit. A read-then-write in Python would let both pass the
    check and both write.

    Raising rolls the surrounding transaction back, releasing anything already
    reserved in this call — which is why the caller must always be atomic.
    """
    for variant_id, quantity in lines:
        updated = ProductVariant.objects.filter(
            pk=variant_id,
            is_active=True,
            stock__gte=F("reserved_stock") + quantity,
        ).update(reserved_stock=F("reserved_stock") + quantity)

        if not updated:
            variant = ProductVariant.objects.filter(pk=variant_id).first()
            label = f"{variant.color} / {variant.size}" if variant else "an item"
            raise InsufficientStock(
                f"{label} sold out while you were checking out."
            )


def commit_stock(lines: Iterable[tuple[int, int]]) -> None:
    """Turn a reservation into a sale: on-hand and reserved both drop.

    Split from :func:`reserve_stock` on purpose. Today both run inside
    ``place_order`` because COD confirms immediately, but a gateway flow
    reserves at checkout and commits on the payment webhook minutes later —
    and that flow needs these to be two separate calls.
    """
    for variant_id, quantity in lines:
        ProductVariant.objects.filter(pk=variant_id).update(
            stock=F("stock") - quantity,
            reserved_stock=F("reserved_stock") - quantity,
        )


def release_stock(lines: Iterable[tuple[int, int]]) -> None:
    """Drop a reservation without selling — the cancel-before-commit path."""
    for variant_id, quantity in lines:
        ProductVariant.objects.filter(
            pk=variant_id, reserved_stock__gte=quantity
        ).update(reserved_stock=F("reserved_stock") - quantity)


def restock(lines: Iterable[tuple[int, int]]) -> None:
    """Put committed units back on the shelf — the cancel-after-commit path."""
    for variant_id, quantity in lines:
        ProductVariant.objects.filter(pk=variant_id).update(
            stock=F("stock") + quantity
        )


def order_stock_lines(order: Order) -> list[tuple[int, int]]:
    """Return ``(variant_id, quantity)`` for every line that still has a variant.

    Lines whose variant was deleted are skipped: there is no row left to
    restock, and the snapshot columns keep the invoice readable regardless.
    """
    return [
        (item.variant_id, item.quantity)
        for item in order.items.all()
        if item.variant_id
    ]


def _resync_products(order: Order) -> None:
    """Refresh cached product stock after an inventory move.

    ``ProductVariant`` writes here go through ``queryset.update()`` for
    atomicity, which skips the signal that normally keeps
    ``Product.total_stock`` in step — so it is refreshed explicitly.
    """
    from apps.products.services import sync_product_stock

    product_ids = {item.product_id for item in order.items.all() if item.product_id}
    for product in Product.objects.filter(pk__in=product_ids):
        sync_product_stock(product)


# ---------------------------------------------------------------------------
# Order creation
# ---------------------------------------------------------------------------


@transaction.atomic
def place_order(
    user: Any,
    *,
    shipping_address_id: Any,
    billing_address_id: Any = None,
    payment_method: str = PaymentMethod.COD,
    delivery_method: str = DeliveryMethod.STANDARD,
    notes: str = "",
) -> Order:
    """Convert the user's cart into an order.

    The whole thing is one transaction. If anything fails — a variant sold out
    between validation and the lock, a constraint rejects a total — nothing is
    written: no order, no reservation, and the cart is untouched. A partially
    created order is far worse than a failed checkout.

    Sequence:

    1. lock the cart lines so a second tab cannot mutate them mid-flight;
    2. re-validate availability *under the lock*, not just before it;
    3. reserve stock with conditional updates;
    4. create the order and its lines from the cart's snapshots;
    5. commit stock, because a placed order is a sale;
    6. deactivate the cart and hand back a fresh empty one.
    """
    assert_payment_method(payment_method)

    cart = get_or_create_cart(user=user)
    recalculate_cart(cart)

    # Lock the lines for the rest of the transaction. Without this, a second
    # "Place order" from another tab reads the same rows and creates a
    # duplicate order from a cart that is already being consumed.
    locked_items = list(
        CartItem.objects.select_for_update()
        .filter(cart=cart, saved_for_later=False)
        .select_related("product", "variant")
    )

    if not locked_items:
        raise BusinessRuleViolation("Your bag is empty.")

    # Re-check under the lock. The pre-checkout check was advisory; this one
    # is the one that counts.
    assert_checkout_ready(cart)

    shipping = resolve_address(user, shipping_address_id)
    billing = (
        resolve_address(user, billing_address_id) if billing_address_id else shipping
    )

    shipping_snapshot = snapshot_address(shipping)
    billing_snapshot = snapshot_address(billing)
    validate_address_snapshot(shipping_snapshot)
    validate_address_snapshot(billing_snapshot)

    summary = get_cart_summary(cart)
    lines = [(item.variant_id, item.quantity) for item in locked_items]

    reserve_stock(lines)

    order = Order.objects.create(
        order_number=_unique_order_number(),
        user=user,
        shipping_address=shipping_snapshot,
        billing_address=billing_snapshot,
        subtotal=summary["subtotal"],
        discount=summary["discount"],
        coupon_code=summary["coupon_code"],
        coupon_discount=summary["coupon_discount"],
        shipping_charge=summary["shipping"],
        platform_fee=summary["platform_fee"],
        tax=summary["tax"],
        grand_total=summary["grand_total"],
        currency=summary["currency"],
        payment_method=payment_method,
        payment_status=PaymentStatus.PENDING,
        status=OrderStatus.PENDING,
        delivery_method=delivery_method,
        estimated_delivery_date=estimate_delivery_date(
            summary["estimated_delivery_days"], delivery_method
        ),
        notes=notes,
    )

    OrderItem.objects.bulk_create(
        [_build_order_item(order, item) for item in locked_items]
    )

    commit_stock(lines)
    Order.objects.filter(pk=order.pk).update(stock_committed=True)
    order.stock_committed = True
    _resync_products(order)
    _credit_purchase_counts(locked_items)

    record_status(order, OrderStatus.PENDING, changed_by=user, remarks="Order placed.")

    # COD needs no gateway, so the order is confirmed immediately. Prepaid
    # methods stay pending until the payments module reports settlement.
    if payment_method in OFFLINE_PAYMENT_METHODS:
        transition_order(
            order,
            OrderStatus.CONFIRMED,
            changed_by=user,
            remarks="Cash on delivery — confirmed automatically.",
        )

    # Deactivate rather than delete: the cart is the evidence of what was
    # bought if a dispute ever needs reconstructing.
    cart.is_active = False
    cart.save(update_fields=["is_active", "updated_at"])

    logger.info(
        "order placed number=%s user_id=%s total=%s method=%s",
        order.order_number,
        user.pk,
        order.grand_total,
        payment_method,
    )
    return order


def _build_order_item(order: Order, item: CartItem) -> OrderItem:
    """Freeze one cart line into an order line.

    Every displayed value is copied here. Nothing on an invoice reads through
    the product foreign key, so a later rename or price change cannot rewrite
    what the customer bought.
    """
    product = item.product
    variant = item.variant
    image = product.primary_image

    return OrderItem(
        order=order,
        product=product,
        variant=variant,
        product_name=product.name,
        product_slug=product.slug,
        brand_name=product.brand.name if product.brand_id else "",
        sku=variant.sku,
        size=variant.size,
        color=variant.color,
        image_url=_image_url(image),
        mrp=item.unit_mrp,
        selling_price=item.unit_price,
        discount=item.discount,
        tax=item.tax,
        quantity=item.quantity,
        subtotal=item.subtotal,
        grand_total=item.total,
    )


def _credit_purchase_counts(items: Iterable[CartItem]) -> None:
    """Add each line's units to its product's purchase counter.

    Done explicitly here because order lines are written with ``bulk_create``,
    which does not send ``post_save`` — the signal that normally maintains this
    counter never fires on the checkout path. Applied with ``F()`` so
    concurrent orders each count, and by quantity rather than by line: three
    units of a shirt is three sales, and a bestseller ranking that counts
    baskets is measuring the wrong thing.
    """
    for item in items:
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(
                purchase_count=F("purchase_count") + item.quantity
            )


def _decredit_purchase_counts(order: Order) -> None:
    """Reverse the purchase credit when an order is cancelled.

    A cancelled order is not a sale. Leaving the credit in place inflates the
    bestseller rails with orders that never shipped. The guard keeps the
    ``PositiveIntegerField`` from being driven below zero by a double-fire.
    """
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(
                pk=item.product_id, purchase_count__gte=item.quantity
            ).update(purchase_count=F("purchase_count") - item.quantity)


def _image_url(image: Any) -> str:
    """Return an image's URL, or an empty string when there is none."""
    if image is None or not image.image:
        return ""
    try:
        return image.image.url
    except ValueError:  # pragma: no cover - misconfigured storage
        return ""


def _unique_order_number(attempts: int = 5) -> str:
    """Return an order number no existing order holds.

    The generator is random, so a collision is vanishingly unlikely — but
    "vanishingly unlikely" over millions of orders is "eventually", and the
    unique constraint would turn it into a failed checkout.
    """
    for _ in range(attempts):
        candidate = generate_order_number()
        if not Order.objects.filter(order_number=candidate).exists():
            return candidate
    raise ResourceConflict("Could not allocate an order number. Please retry.")


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


def record_status(
    order: Order,
    status: str,
    *,
    previous: str = "",
    changed_by: Any = None,
    remarks: str = "",
) -> OrderStatusHistory:
    """Append one entry to the order's timeline."""
    return OrderStatusHistory.objects.create(
        order=order,
        previous_status=previous,
        status=status,
        changed_by=changed_by if changed_by and changed_by.is_authenticated else None,
        remarks=remarks[:255],
    )


@transaction.atomic
def transition_order(
    order: Order,
    target: str,
    *,
    changed_by: Any = None,
    remarks: str = "",
) -> Order:
    """Move an order to ``target``, recording the change.

    The only writer of ``Order.status``. Everything else — the customer cancel
    endpoint, admin bulk actions, the future payment webhook — routes through
    here, so an illegal move is impossible and every move is logged.
    """
    current = order.status

    try:
        assert_transition(current, target)
    except DjangoValidationError as exc:
        raise BusinessRuleViolation(exc.messages[0]) from exc

    order.status = target
    updates = ["status", "updated_at"]

    if target == OrderStatus.DELIVERED:
        order.delivered_at = timezone.now()
        order.delivery_status = DeliveryStatus.DELIVERED
        updates += ["delivered_at", "delivery_status"]
        # A delivered COD parcel is a paid order — the courier collected.
        if order.is_cod and order.payment_status != PaymentStatus.PAID:
            order.payment_status = PaymentStatus.PAID
            updates.append("payment_status")

    elif target == OrderStatus.SHIPPED:
        order.delivery_status = DeliveryStatus.DISPATCHED
        updates.append("delivery_status")

    elif target == OrderStatus.OUT_FOR_DELIVERY:
        order.delivery_status = DeliveryStatus.OUT_FOR_DELIVERY
        updates.append("delivery_status")

    elif target == OrderStatus.CANCELLED:
        order.cancelled_at = timezone.now()
        updates.append("cancelled_at")

    order.save(update_fields=updates)
    record_status(order, target, previous=current, changed_by=changed_by, remarks=remarks)

    logger.info(
        "order %s moved %s -> %s", order.order_number, current, target
    )
    return order


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


@transaction.atomic
def cancel_order(order: Order, *, reason: str, cancelled_by: Any = None) -> Order:
    """Cancel an order and return its inventory to circulation.

    Which inventory operation runs depends on ``stock_committed``: an order
    whose units were already decremented needs them put back, one still only
    reserved needs the reservation dropped. Getting that backwards either
    loses stock permanently or invents it.
    """
    locked = Order.objects.select_for_update().get(pk=order.pk)

    if locked.status not in CANCELLABLE_ORDER_STATUSES:
        raise BusinessRuleViolation(
            f"An order that is already {locked.get_status_display().lower()} "
            "cannot be cancelled. Please raise a return instead."
        )

    lines = order_stock_lines(locked)

    if locked.stock_committed:
        restock(lines)
        Order.objects.filter(pk=locked.pk).update(stock_committed=False)
        locked.stock_committed = False
    else:
        release_stock(lines)

    _resync_products(locked)
    _decredit_purchase_counts(locked)

    locked.cancel_reason = reason[:255]
    locked.save(update_fields=["cancel_reason", "updated_at"])

    transition_order(
        locked,
        OrderStatus.CANCELLED,
        changed_by=cancelled_by,
        remarks=f"Cancelled: {reason}"[:255],
    )

    # A cancelled prepaid order owes the customer money. The refund itself
    # belongs to the payments module; this only records that it is due.
    if locked.payment_status == PaymentStatus.PAID:
        Order.objects.filter(pk=locked.pk).update(
            payment_status=PaymentStatus.REFUNDED
        )
        locked.payment_status = PaymentStatus.REFUNDED

    logger.info("order cancelled number=%s reason=%s", locked.order_number, reason)
    return locked


# ---------------------------------------------------------------------------
# Reorder
# ---------------------------------------------------------------------------


@transaction.atomic
def reorder(order: Order, user: Any) -> dict[str, Any]:
    """Put a past order's still-available items back in the bag.

    Partial success is the point: a two-year-old order will usually have a line
    or two that no longer exists, and refusing the whole reorder over one
    discontinued item is worse than adding the rest and saying which were
    skipped.
    """
    from apps.cart.services import add_to_cart

    cart = get_or_create_cart(user=user)
    added: list[str] = []
    skipped: list[dict[str, str]] = []

    for item in order.items.select_related("product", "variant").all():
        if not item.product_id or not item.variant_id:
            skipped.append({"name": item.product_name, "reason": "no_longer_sold"})
            continue

        try:
            add_to_cart(cart, item.product.slug, item.variant.sku, item.quantity)
            added.append(item.product_name)
        except (BusinessRuleViolation, InsufficientStock) as exc:
            skipped.append({"name": item.product_name, "reason": str(exc.detail)})

    if not added:
        raise BusinessRuleViolation(
            "None of the items from that order are available right now."
        )

    return {"cart": cart, "added": added, "skipped": skipped}


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


def ensure_invoice_number(order: Order) -> str:
    """Allocate an invoice number on first use.

    Assigned lazily rather than at order creation because a cancelled order
    that never shipped should not consume a number in the invoice sequence the
    accountant reconciles.
    """
    if order.invoice_number:
        return order.invoice_number

    for _ in range(5):
        candidate = generate_invoice_number()
        if not Order.objects.filter(invoice_number=candidate).exists():
            Order.objects.filter(pk=order.pk).update(invoice_number=candidate)
            order.invoice_number = candidate
            return candidate

    raise ResourceConflict("Could not allocate an invoice number. Please retry.")


def get_invoice_context(order: Order) -> dict[str, Any]:
    """Return the data an invoice renders, from snapshots only."""
    ensure_invoice_number(order)

    return {
        "order": order,
        "invoice_number": order.invoice_number,
        "invoice_date": order.created_at.date(),
        "customer_name": order.shipping_address.get("full_name", ""),
        "shipping_address": order.shipping_address,
        "billing_address": order.billing_address,
        "items": list(order.items.all()),
        "subtotal": order.subtotal,
        "discount": order.discount,
        "coupon_discount": order.coupon_discount,
        "shipping_charge": order.shipping_charge,
        "platform_fee": order.platform_fee,
        "tax": order.tax,
        "grand_total": order.grand_total,
        "currency": order.currency,
        "payment_method": order.get_payment_method_display(),
        "payment_status": order.get_payment_status_display(),
    }


def generate_invoice_pdf(order: Order, *, force: bool = False) -> Any:
    """Render the invoice to a PDF and store it against the order.

    Cached on the order: an invoice is immutable once the order is placed, so
    re-rendering it on every download is wasted CPU on a file that cannot
    change. ``force`` re-renders after a template change.
    """
    from apps.orders.invoices import render_invoice_pdf

    if order.invoice_file and not force:
        return order.invoice_file

    context = get_invoice_context(order)
    content = render_invoice_pdf(context)

    order.invoice_file.save(f"{order.invoice_number}.pdf", content, save=False)
    Order.objects.filter(pk=order.pk).update(
        invoice_file=order.invoice_file.name, invoice_number=order.invoice_number
    )
    return order.invoice_file


# ---------------------------------------------------------------------------
# Shipments and reads
# ---------------------------------------------------------------------------


@transaction.atomic
def create_shipment(
    order: Order,
    *,
    courier_name: str,
    tracking_number: str = "",
    tracking_url: str = "",
    expected_delivery_date: Any = None,
    dispatch: bool = True,
) -> Shipment:
    """Record a parcel against an order, optionally marking it dispatched."""
    shipment = Shipment.objects.create(
        order=order,
        courier_name=courier_name,
        tracking_number=tracking_number,
        tracking_url=tracking_url,
        expected_delivery_date=expected_delivery_date or order.estimated_delivery_date,
        dispatched_at=timezone.now() if dispatch else None,
    )

    if dispatch and order.status == OrderStatus.PACKED:
        transition_order(
            order,
            OrderStatus.SHIPPED,
            remarks=f"Dispatched via {courier_name}.",
        )

    return shipment


def get_orders(user: Any) -> QuerySet[Order]:
    """Return a customer's orders, newest first, ready to render."""
    return Order.objects.for_user(user).with_items().with_totals().order_by("-created_at")


def get_order(user: Any, order_number: str, *, staff: bool = False) -> Order:
    """Return one order by number, scoped to its owner unless staff.

    Scoping by user is what makes order numbers safe to put in URLs and emails:
    guessing another customer's number yields a 404, not their invoice.
    """
    queryset = Order.objects.with_detail()
    if not staff:
        queryset = queryset.for_user(user)

    order = queryset.filter(order_number=order_number).first()
    if order is None:
        raise BusinessRuleViolation("Order not found.")
    return order


def get_tracking(order: Order) -> dict[str, Any]:
    """Return the tracking timeline the order-tracking page renders."""
    shipment = order.latest_shipment()

    return {
        "order_number": order.order_number,
        "status": order.status,
        "status_display": order.get_status_display(),
        "delivery_status": order.delivery_status,
        "delivery_status_display": order.get_delivery_status_display(),
        "estimated_delivery_date": order.estimated_delivery_date,
        "delivered_at": order.delivered_at,
        "courier_name": shipment.courier_name if shipment else "",
        "tracking_number": shipment.tracking_number if shipment else "",
        "tracking_url": shipment.tracking_url if shipment else "",
        "dispatched_at": shipment.dispatched_at if shipment else None,
        "timeline": [
            {
                "status": entry.status,
                "status_display": entry.get_status_display(),
                "remarks": entry.remarks,
                "at": entry.created_at,
            }
            for entry in order.status_history.all()
        ],
    }


def request_return(order: Order, *, reason: str, requested_by: Any = None) -> Order:
    """Record a return request. **Placeholder — no reverse logistics yet.**

    The contract a returns module implements from here: check the return window
    against ``delivered_at`` and ``Product.is_returnable``, create a return
    record per line rather than per order, book a reverse pickup, and only then
    move the order to RETURNED.

    Today this validates eligibility and moves the status, so the timeline and
    the customer-facing state are already correct.
    """
    if order.status != OrderStatus.DELIVERED:
        raise BusinessRuleViolation("Only delivered orders can be returned.")

    return transition_order(
        order,
        OrderStatus.RETURNED,
        changed_by=requested_by,
        remarks=f"Return requested: {reason}"[:255],
    )


def process_refund(order: Order, *, remarks: str = "") -> Order:
    """Mark an order refunded. **Placeholder — no money moves.**

    The payments module replaces the body: call the gateway's refund API, store
    the refund reference, and only mark the order refunded once the gateway
    confirms. The status transition and audit entry stay exactly as they are.
    """
    if order.status not in {OrderStatus.CANCELLED, OrderStatus.RETURNED}:
        raise BusinessRuleViolation(
            "Only cancelled or returned orders can be refunded."
        )

    order = transition_order(
        order, OrderStatus.REFUNDED, remarks=remarks or "Refund recorded."
    )
    Order.objects.filter(pk=order.pk).update(payment_status=PaymentStatus.REFUNDED)
    order.payment_status = PaymentStatus.REFUNDED
    return order


def mark_payment_settled(
    order: Order, *, reference: str = "", confirm: bool = True
) -> Order:
    """Record that payment succeeded. **The payments module's entry point.**

    Kept here so the payment flow needs no knowledge of the order state
    machine: it calls this, and confirmation plus the audit entry follow.
    """
    Order.objects.filter(pk=order.pk).update(
        payment_status=PaymentStatus.PAID, payment_reference=reference
    )
    order.payment_status = PaymentStatus.PAID
    order.payment_reference = reference

    if confirm and order.status == OrderStatus.PENDING:
        transition_order(
            order, OrderStatus.CONFIRMED, remarks="Payment received."
        )

    return order
