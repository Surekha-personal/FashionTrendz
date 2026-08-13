"""Enumerations shared across every module.

Every value here is a Django ``Choices`` class, so it can be passed straight to
a model field, compared as a constant (``OrderStatus.PAID``) and rendered with
``get_<field>_display()``.

Stored values are stable lowercase strings, never positional integers, so a
value read from the database is self-describing in a log line or a CSV export
and reordering the class can never silently reinterpret existing rows. The two
``IntegerChoices`` classes are the exceptions: their numbers are ordinal and
carry meaning, so arithmetic and ``__gte`` comparisons work in SQL.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """Coarse account type. Fine-grained rights stay with Django permissions."""

    CUSTOMER = "customer", _("Customer")
    STAFF = "staff", _("Staff")
    ADMIN = "admin", _("Admin")


class Gender(models.TextChoices):
    """Canonical gender values for both customer profiles and product targeting."""

    MALE = "male", _("Male")
    FEMALE = "female", _("Female")
    UNISEX = "unisex", _("Unisex")
    OTHER = "other", _("Other")
    UNDISCLOSED = "undisclosed", _("Prefer not to say")


class Currency(models.TextChoices):
    """ISO 4217 codes the storefront can price in."""

    INR = "INR", _("Indian Rupee")
    USD = "USD", _("US Dollar")
    EUR = "EUR", _("Euro")
    GBP = "GBP", _("Pound Sterling")
    AED = "AED", _("UAE Dirham")


class OrderStatus(models.TextChoices):
    """Lifecycle of a customer order.

    Forward path: PENDING to CONFIRMED to PROCESSING to PACKED to SHIPPED to
    OUT_FOR_DELIVERY to DELIVERED. Terminal states are DELIVERED, CANCELLED,
    REFUNDED and RETURNED.
    """

    PENDING = "pending", _("Pending")
    CONFIRMED = "confirmed", _("Confirmed")
    PROCESSING = "processing", _("Processing")
    PACKED = "packed", _("Packed")
    SHIPPED = "shipped", _("Shipped")
    OUT_FOR_DELIVERY = "out_for_delivery", _("Out for delivery")
    DELIVERED = "delivered", _("Delivered")
    CANCELLED = "cancelled", _("Cancelled")
    RETURNED = "returned", _("Returned")
    REFUNDED = "refunded", _("Refunded")


#: Statuses after which an order can no longer change. Kept next to the enum so
#: the order module has one place to consult instead of re-deriving the set.
TERMINAL_ORDER_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.DELIVERED,
        OrderStatus.CANCELLED,
        OrderStatus.RETURNED,
        OrderStatus.REFUNDED,
    }
)

#: Statuses at which a customer may still cancel without support intervention.
#: Cancellation closes once the parcel is with the courier — after that it is a
#: return, which is a different flow with a different refund window.
CANCELLABLE_ORDER_STATUSES: frozenset[str] = frozenset(
    {
        OrderStatus.PENDING,
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
        OrderStatus.PACKED,
    }
)


class PaymentStatus(models.TextChoices):
    """Settlement state of the payment attached to an order."""

    PENDING = "pending", _("Pending")
    AUTHORISED = "authorised", _("Authorised")
    PAID = "paid", _("Paid")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")
    PARTIALLY_REFUNDED = "partially_refunded", _("Partially refunded")
    REFUNDED = "refunded", _("Refunded")


class PaymentMethod(models.TextChoices):
    """How the customer paid."""

    CARD = "card", _("Credit / debit card")
    UPI = "upi", _("UPI")
    NET_BANKING = "net_banking", _("Net banking")
    WALLET = "wallet", _("Wallet")
    COD = "cod", _("Cash on delivery")


class StockStatus(models.TextChoices):
    """Availability label shown on a product listing.

    Derived from the quantity on hand rather than stored independently, so it
    can never disagree with the number it describes.
    """

    IN_STOCK = "in_stock", _("In stock")
    LOW_STOCK = "low_stock", _("Low stock")
    OUT_OF_STOCK = "out_of_stock", _("Out of stock")
    DISCONTINUED = "discontinued", _("Discontinued")


class AddressType(models.TextChoices):
    """What an address is used for at checkout."""

    HOME = "home", _("Home")
    WORK = "work", _("Work")
    BILLING = "billing", _("Billing")
    SHIPPING = "shipping", _("Shipping")
    OTHER = "other", _("Other")


class CouponType(models.TextChoices):
    """How a coupon reduces the cart total."""

    PERCENTAGE = "percentage", _("Percentage off")
    FIXED_AMOUNT = "fixed_amount", _("Fixed amount off")
    FREE_SHIPPING = "free_shipping", _("Free shipping")
    BUY_X_GET_Y = "buy_x_get_y", _("Buy X get Y")


class NotificationType(models.TextChoices):
    """Category of an outbound customer notification."""

    ORDER_PLACED = "order_placed", _("Order placed")
    ORDER_SHIPPED = "order_shipped", _("Order shipped")
    ORDER_DELIVERED = "order_delivered", _("Order delivered")
    ORDER_CANCELLED = "order_cancelled", _("Order cancelled")
    PAYMENT_RECEIVED = "payment_received", _("Payment received")
    PAYMENT_FAILED = "payment_failed", _("Payment failed")
    PRICE_DROP = "price_drop", _("Price drop")
    BACK_IN_STOCK = "back_in_stock", _("Back in stock")
    PROMOTION = "promotion", _("Promotion")
    ACCOUNT = "account", _("Account")


class NotificationChannel(models.TextChoices):
    """Transport a notification is delivered over."""

    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push")
    IN_APP = "in_app", _("In-app")


class PublishStatus(models.TextChoices):
    """Editorial state for any publishable record.

    Used by :class:`apps.core.mixins.PublishStatusMixin`.
    """

    DRAFT = "draft", _("Draft")
    PUBLISHED = "published", _("Published")
    ARCHIVED = "archived", _("Archived")


class Rating(models.IntegerChoices):
    """Star rating on a product review.

    Integer-backed on purpose: the values are ordinal, so ``AVG(rating)`` and
    ``rating__gte=4`` are meaningful in SQL. A text enum would force casting.
    """

    ONE_STAR = 1, _("1 star")
    TWO_STARS = 2, _("2 stars")
    THREE_STARS = 3, _("3 stars")
    FOUR_STARS = 4, _("4 stars")
    FIVE_STARS = 5, _("5 stars")


class Priority(models.IntegerChoices):
    """Processing priority for queued work such as notifications.

    Ordered so ``priority__gte=Priority.HIGH`` selects the urgent tail and
    ``ORDER BY priority DESC`` drains the queue in the right sequence.
    """

    LOW = 10, _("Low")
    NORMAL = 20, _("Normal")
    HIGH = 30, _("High")
    URGENT = 40, _("Urgent")
