"""Shopping cart models.

A cart belongs to exactly one of two things: a signed-in user, or an anonymous
session. The database enforces that with a check constraint, and two partial
unique indexes keep one active cart per owner — a customer with two carts is a
support ticket about a "disappearing" bag.

Stock is **never** touched here. Adding to a cart reserves nothing; reservation
happens at checkout. A cart that holds inventory lets anyone empty the store by
filling a bag and walking away.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.cart.managers import CartItemManager, CartManager
from apps.core.constants import DEFAULT_CURRENCY, PRICE_DECIMAL_PLACES, PRICE_MAX_DIGITS
from apps.core.choices import Currency
from apps.core.mixins import BaseModel
from apps.core.utils import quantise_money
from apps.products.models import Product, ProductVariant

#: Units of one variant a single cart line may hold. Caps both fat-finger
#: entry and the bot that adds 10,000 units to deny stock to real shoppers.
MAX_QUANTITY_PER_LINE: int = 10

#: Distinct lines a cart may hold, for the same reason.
MAX_LINES_PER_CART: int = 50


class Cart(BaseModel):
    """A shopping bag, owned by a user or by an anonymous session."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
        null=True,
        blank=True,
        verbose_name=_("user"),
    )
    session_key = models.CharField(
        _("session key"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Identifies a guest cart before the shopper signs in."),
    )

    is_active = models.BooleanField(
        _("active"),
        default=True,
        db_index=True,
        help_text=_("Cleared when the cart is converted into an order."),
    )

    # Coupon placeholder. The code is captured and echoed back so the cart page
    # can show what was entered; validation and discount live in the future
    # coupon module. See apps.cart.services.apply_coupon.
    coupon_code = models.CharField(
        _("coupon code"),
        max_length=40,
        blank=True,
        help_text=_("Captured for the future coupon module; not yet validated."),
    )
    coupon_discount = models.DecimalField(
        _("coupon discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        editable=False,
    )

    currency = models.CharField(
        _("currency"), max_length=3, choices=Currency.choices, default=DEFAULT_CURRENCY
    )

    objects = CartManager()

    class Meta:
        verbose_name = _("cart")
        verbose_name_plural = _("carts")
        ordering = ["-updated_at"]
        constraints = [
            # A cart is owned by a user or by a session, never both and never
            # neither. Without this, a NULL/NULL row is an orphan nobody can
            # reach and nobody notices until the table is full of them.
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, session_key="")
                    | models.Q(user__isnull=True, session_key__gt="")
                ),
                name="cart_owned_by_user_xor_session",
            ),
            # One active cart per signed-in customer.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_active=True, user__isnull=False),
                name="unique_active_cart_per_user",
            ),
            # One active cart per guest session.
            models.UniqueConstraint(
                fields=["session_key"],
                condition=models.Q(is_active=True, user__isnull=True),
                name="unique_active_cart_per_session",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"], name="cart_user_active_idx"),
            models.Index(
                fields=["session_key", "is_active"], name="cart_session_active_idx"
            ),
            models.Index(fields=["is_active", "-updated_at"], name="cart_abandoned_idx"),
        ]

    def __str__(self) -> str:
        owner = self.user.email if self.user_id else f"guest:{self.session_key[:8]}"
        return f"Cart of {owner}"

    @property
    def is_guest(self) -> bool:
        """Return whether this cart belongs to an anonymous session."""
        return self.user_id is None

    @property
    def active_items(self) -> Any:
        """Return the lines that count towards the total."""
        return self.items.filter(saved_for_later=False)

    @property
    def saved_items(self) -> Any:
        """Return the saved-for-later lines."""
        return self.items.filter(saved_for_later=True)

    @property
    def line_count(self) -> int:
        """Return the number of distinct purchasable lines."""
        annotated = getattr(self, "_line_count", None)
        if annotated is not None:
            return annotated
        return self.active_items.count()

    @property
    def unit_count(self) -> int:
        """Return the total units, which is what the navbar badge shows.

        Units rather than lines: a bag holding three of one shirt reads "3" to
        a shopper, not "1".
        """
        annotated = getattr(self, "_unit_count", None)
        if annotated is not None:
            return annotated or 0
        return self.active_items.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def is_empty(self) -> bool:
        """Return whether there is nothing to check out."""
        return self.line_count == 0


class CartItem(BaseModel):
    """One purchasable line: a variant, a quantity, and its money.

    The five money columns are a **snapshot**, recomputed from the live product
    and variant by :func:`apps.cart.services.recalculate_cart`, which every
    cart read calls first. They are stored rather than derived on read so the
    admin, analytics and the future order-conversion step can see line
    economics without re-deriving them — and so a price change is visible as a
    diff rather than silently swallowed.
    """

    cart = models.ForeignKey(
        Cart, on_delete=models.CASCADE, related_name="items", verbose_name=_("cart")
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("product"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name=_("variant"),
    )

    quantity = models.PositiveSmallIntegerField(_("quantity"), default=1)
    saved_for_later = models.BooleanField(
        _("saved for later"), default=False, db_index=True
    )

    # -- Money snapshot -----------------------------------------------------

    unit_price = models.DecimalField(
        _("unit price"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    unit_mrp = models.DecimalField(
        _("unit MRP"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    discount = models.DecimalField(
        _("line discount"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    tax = models.DecimalField(
        _("line tax"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
    )
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        help_text=_("Unit price times quantity, before tax."),
    )
    total = models.DecimalField(
        _("total"),
        max_digits=PRICE_MAX_DIGITS,
        decimal_places=PRICE_DECIMAL_PLACES,
        default=Decimal("0.00"),
        help_text=_("Subtotal — tax is quoted separately, not added twice."),
    )

    objects = CartItemManager()

    class Meta:
        verbose_name = _("cart item")
        verbose_name_plural = _("cart items")
        ordering = ["saved_for_later", "-created_at"]
        constraints = [
            # One line per variant. Adding the same variant again increases the
            # quantity of the existing line; two rows for "Navy / M" is a cart
            # page showing the same product twice.
            models.UniqueConstraint(
                fields=["cart", "variant"], name="unique_variant_per_cart"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="cartitem_quantity_at_least_one",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__lte=MAX_QUANTITY_PER_LINE),
                name="cartitem_quantity_within_limit",
            ),
        ]
        indexes = [
            models.Index(
                fields=["cart", "saved_for_later"], name="cartitem_cart_saved_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.quantity} x {self.variant}"

    def compute_money(self) -> None:
        """Recompute the money snapshot from the live product and variant.

        Reads ``variant.effective_price``, so a variant-level price override
        wins over the product's base price — which is the whole point of having
        one.
        """
        currency = self.cart.currency if self.cart_id else DEFAULT_CURRENCY

        self.unit_price = quantise_money(self.variant.effective_price, currency)
        self.unit_mrp = quantise_money(self.product.mrp, currency)

        unit_discount = max(self.unit_mrp - self.unit_price, Decimal("0.00"))
        self.discount = quantise_money(unit_discount * self.quantity, currency)
        self.subtotal = quantise_money(self.unit_price * self.quantity, currency)
        self.tax = quantise_money(
            self.subtotal * self.product.tax_percentage / Decimal("100"), currency
        )
        # Tax is quoted separately in the summary rather than added here, so a
        # tax-inclusive storefront price is never charged twice.
        self.total = self.subtotal

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Refresh the money snapshot before every write."""
        if self.product_id and self.variant_id:
            self.compute_money()
        super().save(*args, **kwargs)

    @property
    def added_at(self) -> Any:
        """Alias for ``created_at``, matching the storefront's vocabulary."""
        return self.created_at

    @property
    def available_stock(self) -> int:
        """Return how many units of this variant can still be bought."""
        return self.variant.available_stock

    @property
    def is_available(self) -> bool:
        """Return whether this line can be checked out as it stands."""
        return (
            self.product.is_visible
            and self.variant.is_active
            and self.variant.available_stock >= self.quantity
        )
