"""Seed wishlists, carts and notifications.

Three small tables that share one shape — a customer, a product, a timestamp —
so they share one command rather than three near-identical ones.

Carts are written through ``cart.services.add_to_cart`` rather than by creating
rows directly. The service computes the line money and refreshes the cart
totals; bypassing it produces carts whose stored subtotal disagrees with their
own lines, which is exactly the bug the stored totals exist to prevent.
"""

from __future__ import annotations

import random
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.cart import services as cart_services
from apps.cart.models import Cart, CartItem
from apps.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationPreference,
    NotificationStatus,
)
from apps.products.models import Product
from apps.users.models import User
from apps.wishlist.models import Wishlist, WishlistItem

#: In-app notification copy, keyed by the event it stands in for.
NOTIFICATIONS: list[tuple[str, str, str, str]] = [
    ("order_placed", NotificationCategory.ORDER, "Order {ref} confirmed",
     "Thanks for your order. We have received order {ref} and will email you "
     "as soon as it ships."),
    ("order_shipped", NotificationCategory.ORDER, "Order {ref} has shipped",
     "Your order is on its way. Track it from your account."),
    ("order_delivered", NotificationCategory.ORDER, "Order {ref} delivered",
     "Your order has been delivered. We hope it is everything you expected."),
    ("payment_success", NotificationCategory.PAYMENT, "Payment received for {ref}",
     "We have received your payment. A receipt is in your email."),
    ("refund_completed", NotificationCategory.PAYMENT, "Refund completed for {ref}",
     "Your refund has been processed and should reach your account within "
     "5 to 7 working days."),
    ("review_reminder", NotificationCategory.REVIEW, "How was your order?",
     "You bought something from us recently. A few words about it helps the "
     "next shopper decide."),
    ("coupon_expiring", NotificationCategory.MARKETING, "Your coupon expires soon",
     "TRENDZ10 expires in 3 days. Use it before it goes."),
    ("welcome", NotificationCategory.ACCOUNT, "Welcome to Fashion Trendz",
     "Your account is ready. Browse the new season and save what you like."),
]


class Command(BaseCommand):
    """Populate wishlists, carts and the notification inbox."""

    help = "Seed wishlists, carts and notifications."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--wishlist-rate", type=float, default=0.55,
            help="Share of customers with a wishlist. Default 0.55.",
        )
        parser.add_argument(
            "--cart-rate", type=float, default=0.30,
            help="Share of customers with an active cart. Default 0.30.",
        )
        parser.add_argument(
            "--notifications-per-user", type=int, default=6,
            help="Maximum in-app notifications per customer.",
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--flush", action="store_true",
            help="Delete existing wishlists, carts and notifications first.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed engagement data, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])

        customers = list(User.objects.filter(is_staff=False, is_active=True))
        products = list(
            Product.objects.filter(is_active=True, total_stock__gt=0)
            .prefetch_related("variants")[:600]
        )

        if not customers:
            raise CommandError("No customers found. Run seed_users first.")
        if not products:
            raise CommandError("No in-stock products found. Run seed_products first.")

        if options["flush"]:
            Notification.objects.all().delete()
            CartItem.objects.all().delete()
            Cart.objects.all().delete()
            WishlistItem.objects.all().delete()
            Wishlist.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING("Cleared engagement tables."))

        counts = {
            "wishlists": 0, "wishlist items": 0,
            "carts": 0, "cart lines": 0,
            "notifications": 0, "preferences": 0,
        }

        for customer in customers:
            # One independent stream per concern, seeded from the customer id.
            #
            # A single shared stream is not enough. The wishlist step returns
            # early when the customer already has one, consuming no draws — so
            # on a second run the cart coin flip landed on a different value
            # and a customer who had no cart suddenly got one. Separate streams
            # mean one branch short-circuiting cannot shift another's decision.
            seed = options["seed"]
            wish_rng = random.Random(f"{seed}:wishlist:{customer.pk}")
            cart_rng = random.Random(f"{seed}:cart:{customer.pk}")
            notif_rng = random.Random(f"{seed}:notify:{customer.pk}")
            pref_rng = random.Random(f"{seed}:prefs:{customer.pk}")

            if wish_rng.random() < options["wishlist_rate"]:
                created, items = self._seed_wishlist(customer, products, wish_rng)
                counts["wishlists"] += created
                counts["wishlist items"] += items

            if cart_rng.random() < options["cart_rate"]:
                created, lines = self._seed_cart(customer, products, cart_rng)
                counts["carts"] += created
                counts["cart lines"] += lines

            counts["notifications"] += self._seed_notifications(
                customer, notif_rng, options["notifications_per_user"]
            )
            counts["preferences"] += self._seed_preference(customer, pref_rng)

        if verbosity:
            self.stdout.write(self.style.SUCCESS("Engagement seeded:"))
            for label, value in counts.items():
                self.stdout.write(f"  {label:<16} {value}")
            self.stdout.write(f"  total wishlists  {Wishlist.objects.count()}")
            self.stdout.write(f"  active carts     "
                              f"{Cart.objects.filter(is_active=True).count()}")
            self.stdout.write(f"  total notifs     {Notification.objects.count()}")

    # -- parts --------------------------------------------------------------

    def _seed_wishlist(
        self, customer: User, products: list[Product], rng: random.Random
    ) -> tuple[int, int]:
        """Give a customer a wishlist of three to twelve saved products."""
        wishlist, created = Wishlist.objects.get_or_create(user=customer)
        if wishlist.items.exists():
            return int(created), 0

        chosen = rng.sample(products, k=min(rng.randint(3, 12), len(products)))
        WishlistItem.objects.bulk_create(
            [WishlistItem(wishlist=wishlist, product=product) for product in chosen],
            ignore_conflicts=True,
        )

        # wishlist_count on Product is a denormalised counter the listing rails
        # sort on, so it has to move with the rows.
        for product in chosen:
            Product.objects.filter(pk=product.pk).update(
                wishlist_count=WishlistItem.objects.filter(product=product).count()
            )
        return int(created), len(chosen)

    def _seed_cart(
        self, customer: User, products: list[Product], rng: random.Random
    ) -> tuple[int, int]:
        """Give a customer an active cart with one to five lines."""
        # Guard on the cart existing, not on it having lines. A customer whose
        # sampled products all turned out to be sold out gets an empty cart,
        # and guarding on items meant the next run tried again and added some —
        # so the table crept upward on every pass.
        if Cart.objects.filter(user=customer, is_active=True).exists():
            return 0, 0

        cart = cart_services.get_or_create_cart(user=customer)

        lines = 0
        for product in rng.sample(products, k=min(rng.randint(1, 5), len(products))):
            variants = [v for v in product.variants.all() if v.is_active and v.stock > 0]
            if not variants:
                continue
            variant = rng.choice(variants)
            try:
                cart_services.add_to_cart(
                    cart, product.slug, variant.sku, rng.randint(1, 3)
                )
            except Exception:  # noqa: BLE001 - a sold-out variant is not a seed failure
                continue
            lines += 1

            # A minority of lines are saved for later, so that section of the
            # cart page has something to render.
            if lines and rng.random() < 0.15:
                cart.items.filter(variant=variant).update(saved_for_later=True)

        if not lines:
            return 0, 0

        cart_services.recalculate_cart(cart)
        # Backdate a third of carts past the abandonment window, so the
        # abandoned-cart job and its report have real rows to find.
        if rng.random() < 0.33:
            Cart.objects.filter(pk=cart.pk).update(
                updated_at=timezone.now() - timezone.timedelta(days=rng.randint(2, 20))
            )
        return 1, lines

    def _seed_notifications(
        self, customer: User, rng: random.Random, maximum: int
    ) -> int:
        """Fill the in-app inbox.

        In-app only. The email, SMS and push rows in this table are a delivery
        ledger; inventing sent-mail records for messages nobody sent would make
        the admin's delivery statistics a fiction.
        """
        if Notification.objects.filter(user=customer).exists():
            return 0

        rows = []
        now = timezone.now()
        for index in range(rng.randint(0, maximum)):
            event, category, subject, body = rng.choice(NOTIFICATIONS)
            reference = f"FT-SEED-{rng.randint(1, 9999):07d}"
            rows.append(
                Notification(
                    user=customer,
                    event=event,
                    category=category,
                    channel=NotificationChannel.IN_APP,
                    subject=subject.format(ref=reference),
                    body=body.format(ref=reference),
                    link=f"/orders/{reference}" if "order" in event else "/account",
                    status=NotificationStatus.DELIVERED,
                    is_read=rng.random() < 0.55,
                    sent_at=now - timezone.timedelta(days=rng.randint(0, 90)),
                )
            )

        if not rows:
            return 0

        created = Notification.objects.bulk_create(rows)
        for notification in created:
            if notification.is_read:
                Notification.objects.filter(pk=notification.pk).update(
                    read_at=notification.sent_at
                )
        return len(created)

    def _seed_preference(self, customer: User, rng: random.Random) -> int:
        """Give a customer notification preferences, mostly at the defaults."""
        _, created = NotificationPreference.objects.get_or_create(
            user=customer,
            defaults={
                "email_enabled": True,
                "sms_enabled": rng.random() < 0.8,
                "push_enabled": rng.random() < 0.7,
                # A realistic minority have opted out of marketing, so the
                # opt-out path is exercised by the coupon-expiry job.
                "marketing_enabled": rng.random() < 0.75,
            },
        )
        return int(created)
