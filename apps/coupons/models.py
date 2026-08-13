"""Coupon models.

Two models: the :class:`Coupon` itself and a :class:`CouponUsage` row per
redemption.

Usage is a table rather than a counter because the limits are per-customer
("one per account") as well as global ("first 500 only"), and a single integer
cannot answer "has *this* customer used it". The denormalised ``times_used``
column exists alongside it purely so the global cap can be enforced with a
conditional UPDATE rather than a COUNT under a lock.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Brand, Category
from apps.core.constants import DEFAULT_CURRENCY, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS
from apps.core.mixins import BaseModel
from apps.coupons.managers import CouponManager, CouponUsageManager
from apps.coupons.validators import coupon_code_validator
from apps.products.models import Product


class DiscountType(models.TextChoices):
    """How a coupon reduces the bill."""

    FLAT = "flat", _("Flat amount off")
    PERCENTAGE = "percentage", _("Percentage off")
    FREE_SHIPPING = "free_shipping", _("Free shipping")


class Coupon(BaseModel):
    """A redeemable discount code."""

    code = models.CharField(
        _("code"),
        max_length=40,
        unique=True,
        db_index=True,
        validators=[coupon_code_validator],
        help_text=_("Uppercase. What the customer types at checkout."),
    )
    description = models.CharField(_("description"), max_length=255, blank=True)

    discount_type = models.CharField(
        _("type"),
        max_length=16,
        choices=DiscountType.choices,
        default=DiscountType.PERCENTAGE,
    )
    value = models.DecimalField(
        _("value"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        help_text=_("Percentage (0-100) or flat amount, depending on the type."),
    )
    max_discount = models.DecimalField(
        _("maximum discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        null=True,
        blank=True,
        help_text=_(
            "Caps a percentage coupon. Without it, '50% off' on a ₹90,000 coat "
            "is a ₹45,000 giveaway."
        ),
    )
    min_cart_value = models.DecimalField(
        _("minimum cart value"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    currency = models.CharField(
        _("currency"), max_length=3, default=DEFAULT_CURRENCY
    )

    # -- Limits -------------------------------------------------------------

    max_uses = models.PositiveIntegerField(
        _("maximum uses"),
        default=0,
        help_text=_("Total redemptions allowed across all customers. 0 means unlimited."),
    )
    uses_per_user = models.PositiveSmallIntegerField(
        _("uses per customer"),
        default=1,
        help_text=_("0 means unlimited."),
    )
    times_used = models.PositiveIntegerField(
        _("times used"),
        default=0,
        editable=False,
        help_text=_("Denormalised redemption count, maintained by the service layer."),
    )

    # -- Window -------------------------------------------------------------

    valid_from = models.DateTimeField(_("valid from"), default=timezone.now)
    valid_until = models.DateTimeField(
        _("valid until"),
        null=True,
        blank=True,
        help_text=_("Blank means the coupon never expires."),
    )

    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    is_public = models.BooleanField(
        _("public"),
        default=True,
        db_index=True,
        help_text=_("Show in the storefront's offers list. Turn off for private codes."),
    )
    first_order_only = models.BooleanField(
        _("first order only"),
        default=False,
        help_text=_("Redeemable only by customers who have never ordered."),
    )

    # -- Restrictions -------------------------------------------------------
    # Empty means "applies to everything". A coupon restricted to categories
    # discounts only the qualifying portion of the bag, not the whole total —
    # see apps.coupons.services.eligible_subtotal.

    categories = models.ManyToManyField(
        Category, related_name="coupons", blank=True, verbose_name=_("categories")
    )
    brands = models.ManyToManyField(
        Brand, related_name="coupons", blank=True, verbose_name=_("brands")
    )
    products = models.ManyToManyField(
        Product, related_name="coupons", blank=True, verbose_name=_("products")
    )

    objects = CouponManager()

    class Meta:
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["is_active", "valid_from", "valid_until"], name="coupon_window_idx"),
            models.Index(fields=["is_public", "is_active"], name="coupon_public_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(value__gte=Decimal("0")),
                name="coupon_value_not_negative",
            ),
            models.CheckConstraint(
                condition=models.Q(min_cart_value__gte=Decimal("0")),
                name="coupon_min_cart_not_negative",
            ),
            # A window that closes before it opens is unredeemable and always a
            # data-entry mistake, so the database refuses it outright.
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="coupon_window_ordered",
            ),
        ]

    def __str__(self) -> str:
        return self.code

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalise the code before every write.

        Upper-casing here rather than in a serializer means the uniqueness
        constraint is meaningful no matter which path created the row — API,
        admin, import script or shell.
        """
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    # -- Derived state ------------------------------------------------------

    @property
    def is_expired(self) -> bool:
        """Return whether the validity window has closed."""
        return bool(self.valid_until and self.valid_until < timezone.now())

    @property
    def has_started(self) -> bool:
        """Return whether the validity window has opened."""
        return self.valid_from <= timezone.now()

    @property
    def is_exhausted(self) -> bool:
        """Return whether the global redemption cap has been reached."""
        return bool(self.max_uses and self.times_used >= self.max_uses)

    @property
    def is_redeemable(self) -> bool:
        """Return whether this coupon could be used by somebody right now."""
        return (
            self.is_active
            and self.has_started
            and not self.is_expired
            and not self.is_exhausted
        )

    @property
    def is_restricted(self) -> bool:
        """Return whether this coupon applies to only part of the catalogue."""
        return bool(
            self.categories.exists() or self.brands.exists() or self.products.exists()
        )

    @property
    def remaining_uses(self) -> int | None:
        """Return redemptions left, or None when unlimited."""
        if not self.max_uses:
            return None
        return max(self.max_uses - self.times_used, 0)

    @property
    def display_value(self) -> str:
        """Return the discount as the storefront shows it."""
        if self.discount_type == DiscountType.PERCENTAGE:
            return f"{self.value.normalize()}% OFF"
        if self.discount_type == DiscountType.FLAT:
            # Quantised explicitly: an in-memory Decimal("300") that has not
            # been round-tripped through the database renders as "300", and a
            # price missing its decimals looks like a bug to a shopper.
            return f"{self.currency} {self.value.quantize(Decimal('0.01'))} OFF"
        return "FREE SHIPPING"


class CouponUsage(BaseModel):
    """One redemption of a coupon by one customer on one order.

    Kept even after a cancellation — flagged released rather than deleted — so
    the campaign report still shows how many people tried the code, which is a
    different and equally useful number from how many kept it.
    """

    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name="usages", verbose_name=_("coupon")
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_usages",
        verbose_name=_("customer"),
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="coupon_usages",
        null=True,
        blank=True,
        verbose_name=_("order"),
    )

    discount_amount = models.DecimalField(
        _("discount applied"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    is_released = models.BooleanField(
        _("released"),
        default=False,
        db_index=True,
        help_text=_(
            "Set when the order was cancelled, returning the redemption to the "
            "customer's allowance."
        ),
    )
    released_at = models.DateTimeField(_("released at"), null=True, blank=True)

    objects = CouponUsageManager()

    class Meta:
        verbose_name = _("coupon usage")
        verbose_name_plural = _("coupon usages")
        ordering = ["-created_at"]
        constraints = [
            # One redemption row per order. A webhook retry or a double-fired
            # signal must not count the same order twice against the cap.
            models.UniqueConstraint(
                fields=["coupon", "order"],
                condition=models.Q(order__isnull=False),
                name="unique_coupon_usage_per_order",
            ),
        ]
        indexes = [
            models.Index(fields=["coupon", "user"], name="couponusage_coupon_user_idx"),
            models.Index(fields=["user", "-created_at"], name="couponusage_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.coupon.code} by {self.user.email}"
