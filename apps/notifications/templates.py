"""The notification template catalogue.

One dict, keyed by event. Each entry declares the channels the event uses, its
category, and a subject and body written as ``str.format`` templates.

A Python dict rather than Django template files or a database table. Files
would mean three artefacts per event (subject, text body, and the loader path)
for messages that are four lines long; a table would mean the copy is data
nobody can review in a pull request and that differs between environments.
This module is the single place a copywriter and a reviewer both look.

Adding an event is one entry here plus one ``notify(...)`` call at the point
the event happens.
"""

from __future__ import annotations

from typing import Any

from apps.notifications.models import NotificationCategory, NotificationChannel

EMAIL = NotificationChannel.EMAIL
IN_APP = NotificationChannel.IN_APP
SMS = NotificationChannel.SMS
PUSH = NotificationChannel.PUSH

SIGNOFF = "\n\n— The Fashion Trendz team"


class Template:
    """One event's copy and routing.

    A small class rather than a bare dict so a missing key is an error at
    import time instead of a ``KeyError`` in a signal handler at 2am.
    """

    __slots__ = ("subject", "body", "channels", "category", "sms", "link")

    def __init__(
        self,
        *,
        subject: str,
        body: str,
        channels: tuple[str, ...],
        category: str,
        sms: str = "",
        link: str = "",
    ) -> None:
        self.subject = subject
        self.body = body
        self.channels = channels
        self.category = category
        # SMS is metered and truncated by carriers, so it gets its own short
        # copy rather than a clipped email body.
        self.sms = sms or subject
        self.link = link

    def render(self, context: dict[str, Any]) -> dict[str, str]:
        """Render this template against ``context``.

        Missing keys render as an empty string rather than raising. A
        notification with a blank order number is worse copy than one with a
        number, but far better than an exception that loses the message and
        takes the surrounding transaction with it.
        """
        safe = _Blanks(context)
        return {
            "subject": self.subject.format_map(safe),
            "body": self.body.format_map(safe),
            "sms": self.sms.format_map(safe),
            "link": self.link.format_map(safe),
        }


class _Blanks(dict):
    """A dict that returns "" for missing keys, for use with ``format_map``."""

    def __missing__(self, key: str) -> str:
        return ""


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, Template] = {
    # -- Account ------------------------------------------------------------
    "welcome": Template(
        subject="Welcome to Fashion Trendz, {first_name}",
        body=(
            "Hi {first_name},\n\n"
            "Your Fashion Trendz account is ready. Browse the new season, save "
            "what you like to your wishlist, and check out whenever you are "
            "ready.\n\n"
            "{frontend_url}" + SIGNOFF
        ),
        sms="Welcome to Fashion Trendz, {first_name}!",
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.ACCOUNT,
        link="/account",
    ),
    "password_reset": Template(
        subject="Reset your Fashion Trendz password",
        body=(
            "Hi {first_name},\n\n"
            "We received a request to reset the password for your Fashion Trendz "
            "account. Open the link below to choose a new one:\n\n"
            "{reset_url}\n\n"
            "This link expires in {timeout_hours} hours and can only be used once.\n\n"
            "If you did not request a password reset you can ignore this email; "
            "your password will not change." + SIGNOFF
        ),
        # Email only, deliberately. A reset link in the in-app inbox is only
        # readable by someone already signed in, who does not need it.
        channels=(EMAIL,),
        category=NotificationCategory.ACCOUNT,
    ),
    "password_changed": Template(
        subject="Your Fashion Trendz password was changed",
        body=(
            "Hi {first_name},\n\n"
            "The password on your Fashion Trendz account was just changed.\n\n"
            "If this was not you, reset your password immediately and contact "
            "support." + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.ACCOUNT,
        link="/account/security",
    ),
    # -- Orders -------------------------------------------------------------
    "order_placed": Template(
        subject="Order {order_number} confirmed",
        body=(
            "Hi {first_name},\n\n"
            "Thanks for your order. We have received order {order_number} for "
            "{currency} {total}.\n\n"
            "We will email you again as soon as it ships.\n\n"
            "Track it here: {frontend_url}/orders/{order_number}" + SIGNOFF
        ),
        sms="Fashion Trendz: order {order_number} confirmed. Total {currency} {total}.",
        channels=(EMAIL, IN_APP, SMS),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_packed": Template(
        subject="Order {order_number} is packed",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} has been packed and is waiting for the "
            "courier." + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_shipped": Template(
        subject="Order {order_number} has shipped",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} is on its way.\n\n"
            "Courier: {courier}\n"
            "Tracking number: {tracking_number}\n\n"
            "Track it here: {frontend_url}/orders/{order_number}" + SIGNOFF
        ),
        sms="Fashion Trendz: order {order_number} shipped. Tracking {tracking_number}.",
        channels=(EMAIL, IN_APP, SMS, PUSH),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_out_for_delivery": Template(
        subject="Order {order_number} is out for delivery",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} is out for delivery and should reach you "
            "today." + SIGNOFF
        ),
        sms="Fashion Trendz: order {order_number} is out for delivery today.",
        channels=(EMAIL, IN_APP, SMS, PUSH),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_delivered": Template(
        subject="Order {order_number} delivered",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} has been delivered. We hope it is everything "
            "you expected.\n\n"
            "Tell others what you think: {frontend_url}/orders/{order_number}" + SIGNOFF
        ),
        sms="Fashion Trendz: order {order_number} delivered.",
        channels=(EMAIL, IN_APP, SMS, PUSH),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_cancelled": Template(
        subject="Order {order_number} cancelled",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} has been cancelled.\n\n"
            "{reason}\n\n"
            "Any payment already taken will be refunded to the original payment "
            "method." + SIGNOFF
        ),
        sms="Fashion Trendz: order {order_number} has been cancelled.",
        channels=(EMAIL, IN_APP, SMS),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "order_reminder": Template(
        subject="Your order {order_number} is still awaiting payment",
        body=(
            "Hi {first_name},\n\n"
            "Order {order_number} is still waiting for payment. It will be "
            "released back to stock if it stays unpaid.\n\n"
            "Complete it here: {frontend_url}/orders/{order_number}" + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
    "abandoned_cart": Template(
        subject="You left {item_count} item(s) in your bag",
        body=(
            "Hi {first_name},\n\n"
            "Your bag is still waiting. Sizes sell out, so finish up when you "
            "are ready.\n\n"
            "{frontend_url}/cart" + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        # Marketing: a customer who has switched off promotions has switched
        # off this one too.
        category=NotificationCategory.MARKETING,
        link="/cart",
    ),
    # -- Payments -----------------------------------------------------------
    "payment_success": Template(
        subject="Payment received for order {order_number}",
        body=(
            "Hi {first_name},\n\n"
            "We have received your payment of {currency} {amount} for order "
            "{order_number}.\n\n"
            "Reference: {reference}" + SIGNOFF
        ),
        sms="Fashion Trendz: payment of {currency} {amount} received for {order_number}.",
        channels=(EMAIL, IN_APP, SMS),
        category=NotificationCategory.PAYMENT,
        link="/orders/{order_number}",
    ),
    "payment_failed": Template(
        subject="Payment failed for order {order_number}",
        body=(
            "Hi {first_name},\n\n"
            "Your payment of {currency} {amount} for order {order_number} did "
            "not go through.\n\n"
            "{reason}\n\n"
            "No money has left your account. Try again here: "
            "{frontend_url}/orders/{order_number}" + SIGNOFF
        ),
        sms="Fashion Trendz: payment for {order_number} failed. Please try again.",
        channels=(EMAIL, IN_APP, SMS),
        category=NotificationCategory.PAYMENT,
        link="/orders/{order_number}",
    ),
    "refund_initiated": Template(
        subject="Refund started for order {order_number}",
        body=(
            "Hi {first_name},\n\n"
            "We have started a refund of {currency} {amount} for order "
            "{order_number}.\n\n"
            "It usually reaches your account within 5 to 7 working days, "
            "depending on your bank." + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.PAYMENT,
        link="/orders/{order_number}",
    ),
    "refund_completed": Template(
        subject="Refund completed for order {order_number}",
        body=(
            "Hi {first_name},\n\n"
            "Your refund of {currency} {amount} for order {order_number} has "
            "been processed.\n\n"
            "Reference: {reference}" + SIGNOFF
        ),
        sms="Fashion Trendz: refund of {currency} {amount} processed for {order_number}.",
        channels=(EMAIL, IN_APP, SMS),
        category=NotificationCategory.PAYMENT,
        link="/orders/{order_number}",
    ),
    # -- Reviews ------------------------------------------------------------
    "review_reminder": Template(
        subject="How was {product_name}?",
        body=(
            "Hi {first_name},\n\n"
            "You bought {product_name} a little while ago. A few words about it "
            "helps the next shopper decide.\n\n"
            "{frontend_url}/account/reviews" + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.REVIEW,
        link="/account/reviews",
    ),
    "review_approved": Template(
        subject="Your review is live",
        body=(
            "Hi {first_name},\n\n"
            "Your review of {product_name} has been published. Thanks for "
            "helping other shoppers." + SIGNOFF
        ),
        channels=(IN_APP,),
        category=NotificationCategory.REVIEW,
        link="/products/{product_slug}",
    ),
    "review_rejected": Template(
        subject="Your review was not published",
        body=(
            "Hi {first_name},\n\n"
            "Your review of {product_name} was not published.\n\n"
            "{reason}\n\n"
            "You are welcome to edit it and submit it again." + SIGNOFF
        ),
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.REVIEW,
        link="/account/reviews",
    ),
    # -- Coupons ------------------------------------------------------------
    "coupon_expiring": Template(
        subject="{code} expires in {days_left} day(s)",
        body=(
            "Hi {first_name},\n\n"
            "Your coupon {code} expires on {expires_on}. It is worth "
            "{discount_display} on orders over {currency} {minimum}.\n\n"
            "{frontend_url}" + SIGNOFF
        ),
        sms="Fashion Trendz: coupon {code} expires in {days_left} day(s).",
        channels=(EMAIL, IN_APP),
        category=NotificationCategory.MARKETING,
        link="/",
    ),
    "coupon_applied": Template(
        subject="Coupon {code} applied",
        body=(
            "Hi {first_name},\n\n"
            "Coupon {code} saved you {currency} {discount} on order "
            "{order_number}." + SIGNOFF
        ),
        channels=(IN_APP,),
        category=NotificationCategory.ORDER,
        link="/orders/{order_number}",
    ),
}


def get_template(event: str) -> Template:
    """Return the template for ``event``.

    Raises ``KeyError`` with the available keys listed, because the usual cause
    is a typo in a ``notify()`` call and the fix is one of the names in the
    message.
    """
    try:
        return TEMPLATES[event]
    except KeyError as exc:
        raise KeyError(
            f"Unknown notification event {event!r}. "
            f"Known events: {', '.join(sorted(TEMPLATES))}"
        ) from exc
