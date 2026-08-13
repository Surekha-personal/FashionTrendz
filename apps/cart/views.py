"""Cart API views. Thin by construction.

Cart resolution is the only interesting part. Every endpoint derives the cart
from the request — the signed-in user, or a guest session key — and never from
a client-supplied identifier. That is what makes ``AllowAny`` safe here: there
is no cart a caller can name that is not already theirs.

Guest identity comes from the ``X-Cart-Session`` header, falling back to the
Django session. A header rather than only a cookie because the Next.js
frontend is on a different origin and holds the key in ``localStorage``; on the
first authenticated request that still carries one, the guest cart is merged
automatically, so signing in never loses a bag.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.cart import services
from apps.cart.models import Cart
from apps.cart.permissions import CartAccessPermission
from apps.cart.serializers import (
    AddToCartSerializer,
    CartCompactSerializer,
    CartLineSerializer,
    CartSerializer,
    CartSummarySerializer,
    ChangeQuantitySerializer,
    CheckoutSummarySerializer,
    CouponSerializer,
    MergeCartSerializer,
    UpdateQuantitySerializer,
)
from apps.core.exceptions import BusinessRuleViolation
from apps.core.responses import success_response

#: Header the Next.js client uses to carry its guest cart identity.
CART_SESSION_HEADER = "HTTP_X_CART_SESSION"

SESSION_PARAM = OpenApiParameter(
    name="X-Cart-Session",
    location=OpenApiParameter.HEADER,
    description="Guest cart session key. Ignored once the caller is signed in.",
    required=False,
    type=str,
)


@extend_schema(tags=["Cart"], parameters=[SESSION_PARAM])
class CartViewSet(viewsets.GenericViewSet):
    """The shopping bag, for guests and signed-in customers alike."""

    permission_classes = [CartAccessPermission]
    serializer_class = CartSerializer
    pagination_class = None

    # -- Resolution ---------------------------------------------------------

    def guest_session_key(self) -> str:
        """Return the guest session key, creating a Django session if needed.

        ``session.create()`` is only called when no key exists at all;
        otherwise every anonymous page view would mint a fresh session and
        orphan the previous bag.
        """
        supplied = self.request.META.get(CART_SESSION_HEADER, "").strip()
        if supplied:
            return supplied[:64]

        session = self.request.session
        if not session.session_key:
            session.create()
        return session.session_key or ""

    def resolve_cart(self, *, create: bool = True) -> Cart | None:
        """Return the caller's cart, merging a guest bag on first sign-in.

        The merge happens here rather than on a login signal because Module 2
        authenticates with JWT, which never fires ``user_logged_in``. Doing it
        at cart-resolution time also means it works no matter which cart
        endpoint the client happens to call first after signing in.
        """
        user = getattr(self.request, "user", None)
        is_authenticated = bool(user and user.is_authenticated)

        if is_authenticated:
            supplied = self.request.META.get(CART_SESSION_HEADER, "").strip()
            if supplied:
                return services.merge_carts(user, supplied[:64])

            if create:
                return services.get_or_create_cart(user=user)
            return services.get_cart(user=user)

        session_key = self.guest_session_key()
        if not session_key:
            return None

        if create:
            return services.get_or_create_cart(session_key=session_key)
        return services.get_cart(session_key=session_key)

    def cart_response(self, cart: Cart, message: str, status_code: int = status.HTTP_200_OK) -> Response:
        """Serialise the whole cart after refreshing its money."""
        services.recalculate_cart(cart)
        serializer = CartSerializer(
            services.load_cart(cart), context=self.get_serializer_context()
        )
        return success_response(serializer.data, message=message, status=status_code)

    # -- Read ---------------------------------------------------------------

    @extend_schema(summary="Get the cart", responses={200: CartSerializer})
    def list(self, request: Request) -> Response:
        """Return the cart page payload."""
        cart = self.resolve_cart()
        if cart is None:
            return success_response(
                {"items": [], "saved_items": [], "summary": None, "issues": []},
                message="Your bag is empty.",
            )
        return self.cart_response(cart, "Cart retrieved.")

    @extend_schema(summary="Cart badge count", responses={200: CartCompactSerializer})
    @action(detail=False, methods=["get"])
    def count(self, request: Request) -> Response:
        """Return the navbar badge count.

        Resolves without creating, so an anonymous visitor browsing the site
        never writes a cart row they will not use.
        """
        cart = self.resolve_cart(create=False)
        subtotal = services.cart_subtotal(cart) if cart else 0
        return success_response(
            {"count": services.get_cart_count(cart), "subtotal": subtotal},
            message="Cart count.",
        )

    @extend_schema(summary="Price summary", responses={200: CartSummarySerializer})
    @action(detail=False, methods=["get"])
    def summary(self, request: Request) -> Response:
        """Return only the price breakdown, for the sticky summary panel."""
        cart = self.resolve_cart()
        if cart is None:
            raise BusinessRuleViolation("Your bag is empty.")

        services.recalculate_cart(cart)
        return success_response(
            CartSummarySerializer(services.get_cart_summary(cart)).data,
            message="Cart summary.",
        )

    @extend_schema(
        summary="Checkout payload",
        description="Cart, totals and any blocking issues, in one call.",
        responses={200: CheckoutSummarySerializer},
    )
    @action(detail=False, methods=["get"])
    def checkout(self, request: Request) -> Response:
        """Return everything the checkout page needs."""
        cart = self.resolve_cart()
        if cart is None or cart.is_empty:
            raise BusinessRuleViolation("Your bag is empty.")

        payload = services.get_checkout_payload(cart)
        return success_response(
            {
                "cart": CartSerializer(
                    payload["cart"], context=self.get_serializer_context()
                ).data,
                "summary": CartSummarySerializer(payload["summary"]).data,
                "issues": payload["issues"],
                "is_checkout_ready": payload["is_checkout_ready"],
            },
            message="Checkout summary.",
        )

    # -- Write --------------------------------------------------------------

    @extend_schema(summary="Add to cart", request=AddToCartSerializer)
    @action(detail=False, methods=["post"])
    def add(self, request: Request) -> Response:
        """Add units of a variant, merging into an existing line."""
        payload = AddToCartSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.add_to_cart(
            cart,
            payload.validated_data["product"],
            payload.validated_data["variant"],
            payload.validated_data["quantity"],
        )
        return self.cart_response(cart, "Added to your bag.", status.HTTP_201_CREATED)

    @extend_schema(summary="Set a line's quantity", request=UpdateQuantitySerializer)
    @action(
        detail=False,
        methods=["post", "patch"],
        url_path="update",
        url_name="update",
    )
    # Named ``update_quantity`` rather than ``update``: ``update`` is one of the
    # ``ModelViewSet`` route method names the router reserves, and decorating it
    # raises ImproperlyConfigured at import. The URL and reverse name are pinned
    # explicitly so the route still reads /api/v1/cart/update/.
    def update_quantity(self, request: Request) -> Response:
        """Set a line's quantity. Zero removes the line."""
        payload = UpdateQuantitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.update_quantity(
            cart, payload.validated_data["variant"], payload.validated_data["quantity"]
        )
        return self.cart_response(cart, "Bag updated.")

    @extend_schema(summary="Increase a line's quantity", request=CartLineSerializer)
    @action(detail=False, methods=["post"])
    def increase(self, request: Request) -> Response:
        """Add one unit to a line."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.change_quantity(cart, payload.validated_data["variant"], 1)
        return self.cart_response(cart, "Bag updated.")

    @extend_schema(summary="Decrease a line's quantity", request=CartLineSerializer)
    @action(detail=False, methods=["post"])
    def decrease(self, request: Request) -> Response:
        """Remove one unit from a line, removing the line at zero."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.change_quantity(cart, payload.validated_data["variant"], -1)
        return self.cart_response(cart, "Bag updated.")

    @extend_schema(summary="Remove a line", request=CartLineSerializer)
    @action(detail=False, methods=["post", "delete"])
    def remove(self, request: Request) -> Response:
        """Remove a line entirely."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.remove_from_cart(cart, payload.validated_data["variant"])
        return self.cart_response(cart, "Removed from your bag.")

    @extend_schema(
        summary="Empty the bag",
        description="Saved-for-later items are kept unless include_saved is true.",
    )
    @action(detail=False, methods=["post", "delete"])
    def clear(self, request: Request) -> Response:
        """Empty the bag."""
        include_saved = str(request.data.get("include_saved", "")).lower() in {
            "true", "1", "yes",
        }
        cart = self.resolve_cart()
        removed = services.clear_cart(cart, include_saved=include_saved)
        return self.cart_response(cart, f"Removed {removed} item(s) from your bag.")

    # -- Move between lists -------------------------------------------------

    @extend_schema(summary="Save a line for later", request=CartLineSerializer)
    @action(detail=False, methods=["post"], url_path="save-for-later")
    def save_for_later(self, request: Request) -> Response:
        """Move a line out of the bag without discarding it."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.save_for_later(cart, payload.validated_data["variant"])
        return self.cart_response(cart, "Saved for later.")

    @extend_schema(summary="Move a saved line back to the bag", request=CartLineSerializer)
    @action(detail=False, methods=["post"], url_path="move-to-bag")
    def move_to_bag(self, request: Request) -> Response:
        """Move a saved line back into the bag, re-checking stock."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        services.move_to_bag(cart, payload.validated_data["variant"])
        return self.cart_response(cart, "Moved to your bag.")

    @extend_schema(
        summary="Move a line to the wishlist",
        description="Requires a signed-in customer — a wishlist belongs to an account.",
        request=CartLineSerializer,
    )
    @action(detail=False, methods=["post"], url_path="move-to-wishlist")
    def move_to_wishlist(self, request: Request) -> Response:
        """Move a cart line into the wishlist."""
        payload = CartLineSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        result = services.move_to_wishlist(cart, payload.validated_data["variant"])

        services.recalculate_cart(cart)
        return success_response(
            {
                "cart": CartSerializer(
                    services.load_cart(cart), context=self.get_serializer_context()
                ).data,
                "wishlist_count": result["wishlist_count"],
            },
            message="Moved to your wishlist.",
        )

    # -- Merge and coupons --------------------------------------------------

    @extend_schema(
        summary="Merge a guest cart",
        description=(
            "Folds a guest bag into the signed-in customer's bag. Usually "
            "unnecessary — sending X-Cart-Session on any cart request merges "
            "automatically — but exposed for an explicit post-login call."
        ),
        request=MergeCartSerializer,
    )
    @action(detail=False, methods=["post"])
    def merge(self, request: Request) -> Response:
        """Merge a guest cart into the signed-in customer's cart."""
        if not request.user.is_authenticated:
            raise BusinessRuleViolation("Sign in to merge a guest bag.")

        payload = MergeCartSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = services.merge_carts(request.user, payload.validated_data["session_key"])
        return self.cart_response(cart, "Bags merged.")

    @extend_schema(
        summary="Apply a coupon (placeholder)",
        description="Captured and echoed back. Validation lands with the coupon module.",
        request=CouponSerializer,
    )
    @action(detail=False, methods=["post"], url_path="apply-coupon")
    def apply_coupon(self, request: Request) -> Response:
        """Capture a coupon code."""
        payload = CouponSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        cart = self.resolve_cart()
        result = services.apply_coupon(cart, payload.validated_data["code"])
        return success_response(result, message=result["message"])

    @extend_schema(summary="Remove the coupon")
    @action(detail=False, methods=["post"], url_path="remove-coupon")
    def remove_coupon(self, request: Request) -> Response:
        """Clear any captured coupon code."""
        cart = self.resolve_cart()
        services.remove_coupon(cart)
        return self.cart_response(cart, "Coupon removed.")
