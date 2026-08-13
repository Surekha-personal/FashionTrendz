"""Seed customer accounts with addresses.

Everything downstream — orders, reviews, wishlists, carts, notifications —
needs customers to hang off, so this runs first in ``seed_everything``.

Passwords are set to one well-known development value. That is safe only
because the command refuses to run against a production environment; see
``handle``.
"""

from __future__ import annotations

import random
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.users.models import Address, User

#: Every seeded account shares this password. Development only.
SEED_PASSWORD = "Tr3ndz!Demo2026"

FIRST_NAMES = [
    "Aditi", "Rhea", "Kavya", "Ananya", "Meera", "Ishita", "Priya", "Sanya",
    "Nisha", "Tara", "Diya", "Riya", "Neha", "Pooja", "Sneha", "Anjali",
    "Arjun", "Rohan", "Vivek", "Karan", "Aditya", "Nikhil", "Rahul", "Siddharth",
    "Aryan", "Kabir", "Dhruv", "Ishaan", "Manav", "Varun", "Yash", "Zain",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Nair", "Reddy", "Patel", "Mehta", "Kapoor",
    "Malhotra", "Chopra", "Banerjee", "Bose", "Gupta", "Joshi", "Rao", "Desai",
    "Pillai", "Menon", "Shetty", "Kulkarni", "Chauhan", "Bhat", "Sinha", "Das",
]

#: (city, state, postal prefix). Real cities so the admin's order list looks
#: like a real order list rather than "City 1, City 2".
CITIES = [
    ("Mumbai", "Maharashtra", "400"), ("Delhi", "Delhi", "110"),
    ("Bengaluru", "Karnataka", "560"), ("Hyderabad", "Telangana", "500"),
    ("Chennai", "Tamil Nadu", "600"), ("Kolkata", "West Bengal", "700"),
    ("Pune", "Maharashtra", "411"), ("Ahmedabad", "Gujarat", "380"),
    ("Jaipur", "Rajasthan", "302"), ("Lucknow", "Uttar Pradesh", "226"),
    ("Kochi", "Kerala", "682"), ("Chandigarh", "Chandigarh", "160"),
    ("Indore", "Madhya Pradesh", "452"), ("Bhubaneswar", "Odisha", "751"),
]
STREETS = [
    "Linking Road", "MG Road", "Park Street", "Brigade Road", "Anna Salai",
    "Church Street", "Residency Road", "Camac Street", "Colaba Causeway",
    "Commercial Street", "Hazratganj", "Ashram Road",
]
GENDERS = ["female", "male", "other", "undisclosed"]


class Command(BaseCommand):
    """Create or update demo customer accounts."""

    help = "Seed customer accounts with addresses."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count", type=int, default=200, help="How many customers to create."
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--domain",
            default="seed.fashiontrendz.local",
            help="Email domain. A non-routable domain keeps demo mail undeliverable.",
        )
        parser.add_argument(
            "--allow-production",
            action="store_true",
            help="Override the production guard. Almost certainly a mistake.",
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed customers, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)

        # Every account below shares one published password. Creating those in
        # a production database would be handing out logins, so the command
        # refuses unless explicitly overridden.
        environment = getattr(settings, "ENVIRONMENT", "development")
        if environment == "production" and not options["allow_production"]:
            raise CommandError(
                "Refusing to seed demo accounts with a shared password into "
                "ENVIRONMENT=production. Pass --allow-production if you are "
                "certain."
            )

        rng = random.Random(options["seed"])
        count = max(1, options["count"])
        domain = options["domain"].lstrip("@")

        created = updated = addresses = 0
        now = timezone.now()

        for index in range(1, count + 1):
            # Seeded per index, not drawn from the shared stream. Customer N
            # must be the same person on every run: drawing from the shared rng
            # made the name depend on how many random calls preceded it, so a
            # re-run produced a different email for the same index and created a
            # second account — which then cascaded into duplicate addresses,
            # wishlists, carts and notifications.
            identity = random.Random(f"{options['seed']}:user:{index}")
            first = identity.choice(FIRST_NAMES)
            last = identity.choice(LAST_NAMES)
            email = f"{first.lower()}.{last.lower()}{index}@{domain}"

            user, was_created = User.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "mobile_number": f"+9198{identity.randint(10_000_000, 99_999_999)}",
                    "gender": identity.choice(GENDERS),
                    "date_of_birth": timezone.datetime(
                        identity.randint(1975, 2006),
                        identity.randint(1, 12),
                        identity.randint(1, 28),
                    ).date(),
                    "is_email_verified": identity.random() < 0.82,
                    "is_mobile_verified": identity.random() < 0.6,
                    "is_active": True,
                },
            )

            if was_created:
                user.set_password(SEED_PASSWORD)
                # Spread signups over two years so the customer-growth chart
                # has a shape instead of a single spike.
                user.created_at = now - timezone.timedelta(
                    days=identity.randint(1, 730), hours=identity.randint(0, 23)
                )
                user.save(update_fields=["password", "created_at"])
                created += 1
            else:
                updated += 1

            addresses += self._seed_addresses(user, identity)

        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Customers: {created} created, {updated} updated "
                    f"(total {User.objects.filter(is_staff=False).count()})."
                )
            )
            self.stdout.write(f"Addresses: {addresses} created "
                              f"(total {Address.objects.count()}).")
            if created:
                self.stdout.write(
                    self.style.WARNING(f"Shared demo password: {SEED_PASSWORD}")
                )

    def _seed_addresses(self, user: User, rng: random.Random) -> int:
        """Give a customer one to three addresses, exactly one default."""
        if user.addresses.exists():
            return 0

        created = 0
        for position in range(rng.randint(1, 3)):
            city, state, prefix = rng.choice(CITIES)
            Address.objects.create(
                user=user,
                full_name=f"{user.first_name} {user.last_name}".strip(),
                mobile=user.mobile_number or f"+9198{rng.randint(10**7, 10**8 - 1)}",
                address_line_1=f"{rng.randint(1, 240)}, {rng.choice(STREETS)}",
                address_line_2=rng.choice(
                    ["", "", f"Flat {rng.randint(101, 1204)}", f"Near {rng.choice(STREETS)}"]
                ),
                city=city,
                state=state,
                country="India",
                postal_code=f"{prefix}{rng.randint(100, 999):03d}"[:6],
                # Only the first is default — the partial unique index allows
                # exactly one per customer and would reject a second.
                is_default=position == 0,
            )
            created += 1
        return created
