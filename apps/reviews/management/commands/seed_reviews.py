"""Seed product reviews, review images and helpful votes.

Reviews are written against **delivered order lines**, not against arbitrary
(user, product) pairs. That is not decoration: ``Review.order_item`` carries a
unique constraint and ``is_verified_purchase`` is only meaningful when there is
a purchase behind it. Seeding reviews any other way produces data the
verified-purchase filter and the eligibility endpoint both disagree with.

Consequence: run ``seed_orders`` first. Without delivered orders this command
has nothing to attach to and says so.
"""

from __future__ import annotations

import random
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from apps.core.choices import OrderStatus
from apps.core.seed_assets import AssetLibrary, close_all
from apps.orders.models import OrderItem
from apps.products.models import Product
from apps.reviews.models import HelpfulVote, ModerationStatus, Review, ReviewImage
from apps.reviews.services import recompute_product_rating
from apps.users.models import User

#: Review copy by star band. Written out rather than generated so the seeded
#: review list reads like real customers instead of Lorem Ipsum.
COPY: dict[int, list[tuple[str, str]]] = {
    5: [
        ("Exactly as pictured",
         "The fabric feels far better than the price suggests and the fit is true "
         "to the size chart. Washed it twice with no fading."),
        ("Perfect for the occasion",
         "Wore this to a family wedding and got asked where it was from three "
         "times. The stitching is clean throughout."),
        ("Worth every rupee",
         "Delivered two days early. The colour matches the photographs almost "
         "exactly, which is rare when ordering online."),
        ("Buying a second one",
         "Comfortable enough for a full working day and it does not crease as "
         "much as I expected. Already ordered another colour."),
        ("Excellent quality",
         "Heavier fabric than I anticipated in the best way. Holds its shape "
         "after a full day of wear."),
    ],
    4: [
        ("Very good, sizing runs small",
         "Lovely material and finish, but I would size up. The M fit closer to "
         "an S on me."),
        ("Happy with it",
         "Good value overall. The colour is a shade darker than the listing "
         "photo but I still like it."),
        ("Nearly perfect",
         "Comfortable and well made. Only complaint is that the pockets are "
         "shallower than they look."),
        ("Good buy",
         "Fabric quality is solid and delivery was quick. Docking a star "
         "because the length was slightly longer than expected."),
    ],
    3: [
        ("Decent, not exceptional",
         "It does the job but the fabric is thinner than I hoped for this "
         "price. Fit is accurate at least."),
        ("Mixed feelings",
         "Looks good on but the finish around the seams could be neater. "
         "Acceptable for occasional wear."),
        ("Average",
         "Nothing wrong with it exactly, just did not feel special. The colour "
         "is noticeably lighter in person."),
    ],
    2: [
        ("Not as described",
         "The material feels synthetic despite the listing. Fit was also much "
         "looser than the size chart suggested."),
        ("Disappointing finish",
         "Loose threads at two seams straight out of the packet. Returning it."),
    ],
    1: [
        ("Poor quality",
         "Fabric started pilling after a single wash. Not what I expected at "
         "this price point."),
        ("Wrong fit entirely",
         "Ordered my usual size and it was unwearable. The size chart is not "
         "accurate for this item."),
    ],
}

#: Star distribution. Skewed positive, the way real catalogue reviews are — a
#: flat distribution makes every product average exactly three stars and the
#: rating filter useless.
RATING_WEIGHTS = [(5, 52), (4, 27), (3, 12), (2, 6), (1, 3)]

REJECTION_REASONS = [
    "Contains contact details.",
    "Does not meet our review guidelines.",
    "Review is about delivery, not the product.",
]


class Command(BaseCommand):
    """Create reviews against delivered purchases."""

    help = "Seed reviews, review images and helpful votes."

    def add_arguments(self, parser: CommandParser) -> None:
        """Register command-line options."""
        parser.add_argument(
            "--count", type=int, default=3000, help="Target number of reviews."
        )
        parser.add_argument(
            "--flush", action="store_true", help="Delete existing reviews first."
        )
        parser.add_argument(
            "--seed", type=int, default=20260804, help="Random seed, for reproducibility."
        )
        parser.add_argument(
            "--image-rate",
            type=float,
            default=0.18,
            help="Share of reviews that carry photographs. Default 0.18.",
        )
        parser.add_argument(
            "--no-images", action="store_true", help="Skip review photographs."
        )
        parser.add_argument(
            "--assets-dir", default="", help="Image library root."
        )
        parser.add_argument(
            "--fetch-remote", action="store_true", help="Download remote manifest URLs."
        )

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Seed reviews, rolling back entirely on any error."""
        verbosity = options.get("verbosity", 1)
        rng = random.Random(options["seed"])

        if options["flush"]:
            deleted, _ = Review.objects.all().delete()
            if verbosity:
                self.stdout.write(self.style.WARNING(f"Deleted {deleted} review row(s)."))

        # Only delivered lines that are not already reviewed. The unique
        # constraint on order_item enforces one review per purchase, so this
        # anti-join is what makes the command idempotent.
        candidates = list(
            OrderItem.objects.filter(
                order__status=OrderStatus.DELIVERED, review__isnull=True
            )
            .select_related("order", "order__user", "product")
            .order_by("id")[: options["count"] * 2]
        )

        if not candidates:
            # Two different situations, and only one is an error. No delivered
            # orders at all means the pipeline ran out of order. Delivered
            # orders that are all already reviewed means there is simply
            # nothing left to do — which is what a second run looks like, and
            # is success, not failure.
            delivered = OrderItem.objects.filter(
                order__status=OrderStatus.DELIVERED
            ).exists()
            if not delivered:
                raise CommandError(
                    "No delivered orders found. Run seed_orders first."
                )
            if verbosity:
                self.stdout.write(
                    f"Reviews: every delivered line is already reviewed "
                    f"(total {Review.objects.count()}), nothing to do."
                )
            return

        rng.shuffle(candidates)
        wanted = min(options["count"], len(candidates))

        library = AssetLibrary(
            options["assets_dir"] or None, fetch_remote=options["fetch_remote"]
        )
        opened: list = []

        created = images = votes = 0
        touched_products: set[int] = set()

        for item in candidates[:wanted]:
            if item.product_id is None:
                continue

            rating = rng.choices(
                [r for r, _ in RATING_WEIGHTS], weights=[w for _, w in RATING_WEIGHTS]
            )[0]
            title, body = rng.choice(COPY[rating])

            # Most reviews are approved; a realistic minority sit pending or
            # rejected so the moderation queue has something in it.
            status = rng.choices(
                [ModerationStatus.APPROVED, ModerationStatus.PENDING,
                 ModerationStatus.REJECTED],
                weights=[86, 9, 5],
            )[0]

            written_at = (item.order.delivered_at or item.order.created_at) + \
                timezone.timedelta(days=rng.randint(1, 30))

            review = Review.objects.create(
                product_id=item.product_id,
                user=item.order.user,
                order_item=item,
                rating=rating,
                title=title,
                body=body,
                is_verified_purchase=True,
                status=status,
                moderated_at=(
                    written_at + timezone.timedelta(hours=rng.randint(1, 48))
                    if status != ModerationStatus.PENDING
                    else None
                ),
                rejection_reason=(
                    rng.choice(REJECTION_REASONS)
                    if status == ModerationStatus.REJECTED
                    else ""
                ),
            )
            Review.objects.filter(pk=review.pk).update(created_at=written_at)
            created += 1
            touched_products.add(item.product_id)

            if (
                not options["no_images"]
                and status == ModerationStatus.APPROVED
                and rng.random() < options["image_rate"]
            ):
                added, handles = self._attach_images(review, library, rng)
                images += added
                opened.extend(handles)

            if status == ModerationStatus.APPROVED:
                votes += self._attach_votes(review, rng)

        close_all(opened)

        # Rating aggregation is approved-only and owned by the reviews service.
        # Recomputing per product once at the end, rather than per review,
        # keeps this to one query per product instead of one per row.
        for product in Product.objects.filter(pk__in=touched_products):
            recompute_product_rating(product)

        if verbosity:
            self.stdout.write(self.style.SUCCESS("Reviews seeded:"))
            self.stdout.write(f"  reviews        {created}")
            self.stdout.write(f"  images         {images}")
            self.stdout.write(f"  helpful votes  {votes}")
            self.stdout.write(f"  products rated {len(touched_products)}")
            self.stdout.write(f"  total reviews  {Review.objects.count()}")
            self.stdout.write(
                f"  approved       "
                f"{Review.objects.filter(status=ModerationStatus.APPROVED).count()}"
            )
            self.stdout.write(f"  assets         {library.summary()}")
            for warning in library.warnings(4):
                self.stdout.write(
                    self.style.WARNING(f"    no images found in seed_assets/{warning}")
                )

    # -- parts --------------------------------------------------------------

    def _attach_images(
        self, review: Review, library: AssetLibrary, rng: random.Random
    ) -> tuple[int, list]:
        """Attach one to three customer photographs from the asset library."""
        files = library.images_from(
            "reviews", key=str(review.uuid), count=rng.randint(1, 3)
        )
        if not files:
            return 0, []

        for index, handle in enumerate(files):
            ReviewImage.objects.create(
                review=review,
                image=handle,
                caption=rng.choice(
                    ["", "", "As worn", "Fabric close-up", "Fit reference"]
                ),
                display_order=index,
            )
        return len(files), files

    def _attach_votes(self, review: Review, rng: random.Random) -> int:
        """Add helpful votes from customers other than the author.

        The counter is set with an UPDATE rather than incremented per vote,
        because the post_delete receiver on HelpfulVote also adjusts it and
        double-counting here would drift the number.
        """
        if rng.random() > 0.35:
            return 0

        voters = list(
            User.objects.filter(is_staff=False)
            .exclude(pk=review.user_id)
            .order_by("?")[: rng.randint(1, 6)]
        )
        if not voters:
            return 0

        HelpfulVote.objects.bulk_create(
            [HelpfulVote(review=review, user=voter) for voter in voters],
            ignore_conflicts=True,
        )
        actual = HelpfulVote.objects.filter(review=review).count()
        Review.objects.filter(pk=review.pk).update(helpful_count=actual)
        return actual
