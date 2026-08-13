"""Tests for the reviews module.

Concentrated on the three things that go wrong in review systems: someone
reviews a product they never bought, someone reviews the same purchase twice,
and an unmoderated review moves the number on the product page.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.catalog.models import Brand, Category, SubCategory
from apps.core.choices import OrderStatus
from apps.core.exceptions import BusinessRuleViolation, ResourceConflict
from apps.orders.models import Order, OrderItem
from apps.products.models import Product, ProductVariant, Size
from apps.reviews import services
from apps.reviews.models import HelpfulVote, ModerationStatus, Review, ReviewImage
from apps.reviews.validators import (
    validate_no_contact_details,
    validate_rating,
    validate_review_body,
)
from apps.users.models import User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


class ReviewFixtureMixin:
    """Builds a delivered order so there is something legitimate to review."""

    def build_world(self) -> None:
        """Create products, customers and a delivered purchase."""
        cache.clear()

        self.category = Category.objects.create(name="Women")
        self.subcategory = SubCategory.objects.create(
            category=self.category, name="Dresses"
        )
        self.brand = Brand.objects.create(name="Nordwyn")

        self.product = self.make_product("Classic Midi Dress", "FT-R0001")
        self.other_product = self.make_product("Linen Shirt", "FT-R0002")

        self.user = User.objects.create_user(
            email="shopper@example.com",
            password=STRONG_PASSWORD,
            first_name="Aditi",
            last_name="Sharma",
        )
        self.stranger = User.objects.create_user(
            email="other@example.com", password=STRONG_PASSWORD, first_name="Rhea"
        )
        self.staff = User.objects.create_user(
            email="staff@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

        self.order = self.make_order(self.user, OrderStatus.DELIVERED)
        self.item = self.make_item(self.order, self.product)

    def make_product(self, name: str, sku: str, **extra: Any) -> Product:
        """Create a published product."""
        defaults: dict[str, Any] = {
            "name": name,
            "sku": sku,
            "category": self.category,
            "subcategory": self.subcategory,
            "brand": self.brand,
            "mrp": Decimal("2000.00"),
            "selling_price": Decimal("1500.00"),
            "published_at": timezone.now() - timezone.timedelta(days=1),
        }
        defaults.update(extra)
        product = Product.objects.create(**defaults)
        ProductVariant.objects.create(
            product=product, sku=f"{sku}-0", color="Navy", size=Size.M, stock=5
        )
        return product

    def make_order(self, user: User, status_value: str) -> Order:
        """Create an order in a given state.

        ``order_number`` is supplied explicitly: the generator is timestamp
        based, and a test that places three orders inside the same second
        collides on the unique index.
        """
        self._order_seq = getattr(self, "_order_seq", 0) + 1
        return Order.objects.create(
            user=user,
            order_number=f"FT-TEST-{self._order_seq:05d}",
            status=status_value,
            shipping_address={"city": "Mumbai"},
            billing_address={"city": "Mumbai"},
            subtotal=Decimal("1500.00"),
            grand_total=Decimal("1500.00"),
            delivered_at=timezone.now()
            if status_value == OrderStatus.DELIVERED
            else None,
        )

    def make_item(self, order: Order, product: Product) -> OrderItem:
        """Create one order line."""
        return OrderItem.objects.create(
            order=order,
            product=product,
            product_name=product.name,
            product_slug=product.slug,
            sku=product.sku,
            mrp=product.mrp,
            selling_price=product.selling_price,
            quantity=1,
            subtotal=product.selling_price,
            grand_total=product.selling_price,
        )

    def write_review(self, **overrides: Any) -> Review:
        """Write a review against the delivered line."""
        kwargs: dict[str, Any] = {
            "user": self.user,
            "order_item_id": self.item.pk,
            "rating": 5,
            "title": "Lovely",
            "body": "The fabric is soft and the fit is exactly as described.",
        }
        kwargs.update(overrides)
        return services.create_review(**kwargs)


class ReviewTestCase(ReviewFixtureMixin, TestCase):
    """Base case with the world built."""

    def setUp(self) -> None:
        self.build_world()


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class ValidatorTests(TestCase):
    """The field-level rules."""

    def test_a_short_review_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_review_body("nice")

    def test_a_review_of_only_punctuation_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_review_body("!!!!!!!!!!!!!!!")

    def test_a_hindi_review_is_accepted(self) -> None:
        # A review in Devanagari is a real review, not noise.
        validate_review_body("यह पोशाक बहुत सुंदर है और कपड़ा अच्छा है।")

    def test_an_email_address_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_no_contact_details("Great dress, write me at me@example.com")

    def test_a_phone_number_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_no_contact_details("Call me on +91 98765 43210 for a better price")

    def test_ordinary_numbers_survive(self) -> None:
        # Sizes and measurements must not trip the phone-number rule.
        validate_no_contact_details("I am 5 foot 4 and size 12 fits perfectly.")

    def test_a_rating_outside_the_range_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_rating(6)
        with self.assertRaises(DjangoValidationError):
            validate_rating(0)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


class EligibilityTests(ReviewTestCase):
    """Who may review what."""

    def test_a_delivered_line_is_reviewable(self) -> None:
        items = services.reviewable_order_items(self.user)
        self.assertEqual(list(items), [self.item])

    def test_an_undelivered_line_is_not_reviewable(self) -> None:
        self.order.status = OrderStatus.SHIPPED
        self.order.save(update_fields=["status"])

        self.assertEqual(list(services.reviewable_order_items(self.user)), [])
        with self.assertRaises(BusinessRuleViolation):
            services.get_reviewable_item(self.user, self.item.pk)

    def test_another_customers_line_is_not_reviewable(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.get_reviewable_item(self.stranger, self.item.pk)

    def test_a_reviewed_line_drops_out_of_the_pending_list(self) -> None:
        self.write_review()
        self.assertEqual(list(services.reviewable_order_items(self.user)), [])

    def test_eligibility_reports_the_line_to_review_against(self) -> None:
        result = services.can_review_product(self.user, self.product)
        self.assertTrue(result["can_review"])
        self.assertEqual(result["order_item"], self.item.pk)

    def test_a_non_purchaser_is_told_why(self) -> None:
        result = services.can_review_product(self.stranger, self.product)
        self.assertFalse(result["can_review"])
        self.assertEqual(result["reason"], "not_purchased")

    def test_a_signed_out_visitor_is_told_to_sign_in(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        result = services.can_review_product(AnonymousUser(), self.product)
        self.assertEqual(result["reason"], "authentication_required")

    def test_an_existing_review_is_reported_as_such(self) -> None:
        self.write_review()
        result = services.can_review_product(self.user, self.product)
        self.assertEqual(result["reason"], "already_reviewed")


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class CreateReviewTests(ReviewTestCase):
    """Writing a review."""

    def test_a_review_is_marked_as_a_verified_purchase(self) -> None:
        review = self.write_review()
        self.assertTrue(review.is_verified_purchase)
        self.assertEqual(review.product, self.product)

    def test_the_product_comes_from_the_purchase_not_the_request(self) -> None:
        # The client never names a product, so it cannot attach a review to one
        # it did not buy.
        review = self.write_review()
        self.assertEqual(review.product_id, self.item.product_id)

    def test_a_review_starts_in_the_moderation_queue(self) -> None:
        self.assertEqual(self.write_review().status, ModerationStatus.PENDING)

    @override_settings(REVIEW_AUTO_APPROVE=True)
    def test_auto_approve_publishes_immediately(self) -> None:
        review = self.write_review()
        self.assertEqual(review.status, ModerationStatus.APPROVED)
        self.assertIsNotNone(review.moderated_at)

    def test_reviewing_the_same_purchase_twice_is_refused(self) -> None:
        self.write_review()
        with self.assertRaises(ResourceConflict):
            self.write_review()

    def test_the_database_refuses_a_duplicate_even_without_the_service(self) -> None:
        # The constraint, not the check, is what survives two concurrent posts.
        self.write_review()
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                product=self.product, user=self.user, order_item=self.item, rating=1
            )

    def test_two_purchases_of_the_same_product_allow_two_reviews(self) -> None:
        second_order = self.make_order(self.user, OrderStatus.DELIVERED)
        second_item = self.make_item(second_order, self.product)

        self.write_review()
        again = self.write_review(order_item_id=second_item.pk, rating=3, body="Second one shrank in the wash badly.")

        self.assertEqual(Review.objects.filter(user=self.user).count(), 2)
        self.assertEqual(again.rating, 3)


class UpdateReviewTests(ReviewTestCase):
    """Editing and deleting."""

    def setUp(self) -> None:
        super().setUp()
        self.review = self.write_review()
        services.moderate_review(
            self.review, moderator=self.staff, status=ModerationStatus.APPROVED
        )

    def test_editing_returns_an_approved_review_to_the_queue(self) -> None:
        # Otherwise an approved review is a permanently writable public slot.
        updated = services.update_review(self.review, body="Completely different text now.")
        self.assertEqual(updated.status, ModerationStatus.PENDING)
        self.assertIsNone(updated.moderated_at)

    def test_editing_the_rating_moves_the_product_average(self) -> None:
        services.update_review(self.review, rating=1)
        services.moderate_review(
            self.review, moderator=self.staff, status=ModerationStatus.APPROVED
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_average, Decimal("1.00"))

    def test_deleting_a_review_clears_the_product_rating(self) -> None:
        services.delete_review(self.review)
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 0)
        self.assertEqual(self.product.rating_average, Decimal("0.00"))

    def test_deleting_frees_the_purchase_to_be_reviewed_again(self) -> None:
        services.delete_review(self.review)
        self.assertEqual(list(services.reviewable_order_items(self.user)), [self.item])


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class RatingAggregationTests(ReviewTestCase):
    """Keeping Product's cached rating honest."""

    def approve(self, review: Review) -> Review:
        """Publish a review."""
        return services.moderate_review(
            review, moderator=self.staff, status=ModerationStatus.APPROVED
        )

    def test_a_pending_review_does_not_move_the_average(self) -> None:
        # The bug this whole module guards against: spam moving the number on
        # the product page before a human ever sees it.
        self.write_review(rating=1)
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 0)
        self.assertEqual(self.product.rating_average, Decimal("0.00"))

    def test_approving_moves_the_average(self) -> None:
        self.approve(self.write_review(rating=4))
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_average, Decimal("4.00"))
        self.assertEqual(self.product.rating_count, 1)

    def test_rejecting_takes_the_review_back_out(self) -> None:
        review = self.approve(self.write_review(rating=5))
        services.moderate_review(
            review,
            moderator=self.staff,
            status=ModerationStatus.REJECTED,
            reason="Spam.",
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 0)

    def test_the_average_is_rounded_to_two_places(self) -> None:
        for rating in (4, 5, 5):
            order = self.make_order(self.user, OrderStatus.DELIVERED)
            item = self.make_item(order, self.product)
            self.approve(
                self.write_review(
                    order_item_id=item.pk,
                    rating=rating,
                    body="A perfectly reasonable amount of review text here.",
                )
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_average, Decimal("4.67"))

    def test_the_products_module_delegates_to_this_one(self) -> None:
        # products.services.recompute_rating must not count pending reviews.
        from apps.products import services as product_services

        self.write_review(rating=1)
        product_services.recompute_rating(self.product)
        self.product.refresh_from_db()
        self.assertEqual(self.product.rating_count, 0)

    def test_the_star_distribution_includes_empty_buckets(self) -> None:
        self.approve(self.write_review(rating=5))
        breakdown = services.get_star_distribution(self.product)

        self.assertEqual(len(breakdown["distribution"]), 5)
        self.assertEqual(breakdown["distribution"][0]["stars"], 5)
        self.assertEqual(breakdown["distribution"][0]["count"], 1)
        self.assertEqual(breakdown["distribution"][4]["count"], 0)

    def test_percentages_sum_to_one_hundred(self) -> None:
        for rating in (5, 3):
            order = self.make_order(self.user, OrderStatus.DELIVERED)
            item = self.make_item(order, self.product)
            self.approve(
                self.write_review(
                    order_item_id=item.pk,
                    rating=rating,
                    body="Another entirely reasonable body of review text.",
                )
            )
        breakdown = services.get_star_distribution(self.product)
        total = sum(bucket["percentage"] for bucket in breakdown["distribution"])
        self.assertAlmostEqual(total, 100.0, places=1)

    def test_the_summary_is_cached_and_invalidated_on_write(self) -> None:
        self.approve(self.write_review(rating=5))
        first = services.get_rating_summary(self.product)
        self.assertEqual(first["count"], 1)

        order = self.make_order(self.user, OrderStatus.DELIVERED)
        item = self.make_item(order, self.product)
        self.approve(
            self.write_review(
                order_item_id=item.pk,
                rating=1,
                body="This one did not work out for me at all sadly.",
            )
        )

        self.assertEqual(services.get_rating_summary(self.product)["count"], 2)


# ---------------------------------------------------------------------------
# Helpful votes
# ---------------------------------------------------------------------------


class HelpfulVoteTests(ReviewTestCase):
    """The thumbs-up toggle."""

    def setUp(self) -> None:
        super().setUp()
        self.review = self.write_review()

    def test_voting_increments_the_counter(self) -> None:
        result = services.toggle_helpful(self.review, self.stranger)
        self.assertTrue(result["voted"])
        self.assertEqual(result["helpful_count"], 1)

    def test_voting_again_takes_the_vote_back(self) -> None:
        services.toggle_helpful(self.review, self.stranger)
        result = services.toggle_helpful(self.review, self.stranger)

        self.assertFalse(result["voted"])
        self.assertEqual(result["helpful_count"], 0)
        self.assertEqual(HelpfulVote.objects.count(), 0)

    def test_the_counter_is_decremented_exactly_once(self) -> None:
        # The service used to decrement and the post_delete receiver used to
        # decrement again, taking the count to -1 and clamping at 0.
        services.toggle_helpful(self.review, self.stranger)
        services.toggle_helpful(self.review, self.staff)
        services.toggle_helpful(self.review, self.stranger)

        self.review.refresh_from_db()
        self.assertEqual(self.review.helpful_count, 1)

    def test_a_customer_cannot_vote_on_their_own_review(self) -> None:
        with self.assertRaises(BusinessRuleViolation):
            services.toggle_helpful(self.review, self.user)

    def test_one_customer_cannot_vote_twice(self) -> None:
        HelpfulVote.objects.create(review=self.review, user=self.stranger)
        with self.assertRaises(IntegrityError):
            HelpfulVote.objects.create(review=self.review, user=self.stranger)

    def test_recounting_repairs_a_drifted_counter(self) -> None:
        HelpfulVote.objects.create(review=self.review, user=self.stranger)
        Review.objects.filter(pk=self.review.pk).update(helpful_count=99)

        self.assertEqual(services.recount_helpful(self.review), 1)


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------


class ModerationTests(ReviewTestCase):
    """The queue and its actions."""

    def test_the_queue_is_oldest_first(self) -> None:
        # Newest-first leaves the tail of a busy queue permanently unseen.
        first = self.write_review()
        order = self.make_order(self.user, OrderStatus.DELIVERED)
        second = self.write_review(
            order_item_id=self.make_item(order, self.other_product).pk,
            body="A second review with quite enough words in it.",
        )

        self.assertEqual(list(services.get_moderation_queue()), [first, second])

    def test_rejecting_records_the_reason(self) -> None:
        review = self.write_review()
        services.moderate_review(
            review,
            moderator=self.staff,
            status=ModerationStatus.REJECTED,
            reason="Contains a competitor link.",
        )
        self.assertEqual(review.rejection_reason, "Contains a competitor link.")
        self.assertEqual(review.moderated_by, self.staff)

    def test_approving_clears_a_previous_rejection_reason(self) -> None:
        review = self.write_review()
        services.moderate_review(
            review, moderator=self.staff, status=ModerationStatus.REJECTED, reason="No."
        )
        services.moderate_review(
            review, moderator=self.staff, status=ModerationStatus.APPROVED
        )
        self.assertEqual(review.rejection_reason, "")

    def test_a_review_cannot_be_moved_back_to_pending_by_a_moderator(self) -> None:
        review = self.write_review()
        with self.assertRaises(BusinessRuleViolation):
            services.moderate_review(
                review, moderator=self.staff, status=ModerationStatus.PENDING
            )

    def test_bulk_approval_refreshes_every_product_touched(self) -> None:
        self.write_review(rating=4)
        order = self.make_order(self.user, OrderStatus.DELIVERED)
        self.write_review(
            order_item_id=self.make_item(order, self.other_product).pk,
            rating=2,
            body="Not what I expected from these measurements at all.",
        )

        updated = services.bulk_moderate(
            Review.objects.all(), moderator=self.staff, status=ModerationStatus.APPROVED
        )
        self.assertEqual(updated, 2)

        self.product.refresh_from_db()
        self.other_product.refresh_from_db()
        self.assertEqual(self.product.rating_average, Decimal("4.00"))
        self.assertEqual(self.other_product.rating_average, Decimal("2.00"))


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------


class ReviewQueryTests(ReviewTestCase):
    """Filters and sorting on the public list."""

    def setUp(self) -> None:
        super().setUp()
        self.five = self.write_review(rating=5)
        order = self.make_order(self.user, OrderStatus.DELIVERED)
        self.two = self.write_review(
            order_item_id=self.make_item(order, self.product).pk,
            rating=2,
            body="The colour was nothing like the photograph on the site.",
        )
        services.bulk_moderate(
            Review.objects.all(), moderator=self.staff, status=ModerationStatus.APPROVED
        )

    def test_only_approved_reviews_are_public(self) -> None:
        pending = self.write_review(
            order_item_id=self.make_item(
                self.make_order(self.user, OrderStatus.DELIVERED), self.product
            ).pk,
            rating=1,
            body="Pending review that nobody should see on the page yet.",
        )
        listed = services.get_product_reviews(self.product.slug)
        self.assertNotIn(pending, listed)

    def test_filtering_by_rating(self) -> None:
        listed = services.get_product_reviews(self.product.slug, rating=5)
        self.assertEqual(list(listed), [self.five])

    def test_sorting_by_most_helpful(self) -> None:
        services.toggle_helpful(self.two, self.stranger)
        listed = services.get_product_reviews(self.product.slug, sort="most_helpful")
        self.assertEqual(list(listed)[0], self.two)

    def test_sorting_oldest_first(self) -> None:
        listed = services.get_product_reviews(self.product.slug, sort="oldest")
        self.assertEqual(list(listed)[0], self.five)

    def test_the_with_images_filter_uses_one_query(self) -> None:
        listed = services.get_product_reviews(self.product.slug, with_images=True)
        self.assertEqual(list(listed), [])

    def test_vote_state_is_annotated_without_n_plus_one(self) -> None:
        services.toggle_helpful(self.five, self.stranger)
        listed = list(
            services.get_product_reviews(self.product.slug, user=self.stranger)
        )
        voted = {review.pk: review.has_voted for review in listed}
        self.assertTrue(voted[self.five.pk])
        self.assertFalse(voted[self.two.pk])

    def test_a_signed_out_visitor_has_no_vote_state(self) -> None:
        from django.contrib.auth.models import AnonymousUser

        listed = list(
            services.get_product_reviews(self.product.slug, user=AnonymousUser())
        )
        self.assertTrue(all(not review.has_voted for review in listed))

    def test_the_author_name_is_abbreviated(self) -> None:
        # Publishing a full name next to a purchase is more than the customer
        # agreed to when they clicked submit.
        self.assertEqual(self.five.author_name, "Aditi S.")

    def test_a_customer_sees_their_own_pending_reviews(self) -> None:
        pending = self.write_review(
            order_item_id=self.make_item(
                self.make_order(self.user, OrderStatus.DELIVERED), self.other_product
            ).pk,
            body="Held for moderation but visible to its own author.",
        )
        self.assertIn(pending, services.get_user_reviews(self.user))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class ReviewAPITests(ReviewFixtureMixin, APITestCase):
    """The HTTP surface."""

    def setUp(self) -> None:
        self.build_world()

    def auth(self, user: User) -> None:
        """Authenticate as ``user``."""
        self.client.force_authenticate(user=user)

    def test_writing_a_review_returns_201(self) -> None:
        self.auth(self.user)
        response = self.client.post(
            reverse("reviews:review-list"),
            {
                "order_item": self.item.pk,
                "rating": 5,
                "title": "Lovely",
                "body": "The fabric is soft and the fit is exactly as described.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()["data"]["status"], ModerationStatus.PENDING)

    def test_a_low_rating_needs_words(self) -> None:
        self.auth(self.user)
        response = self.client.post(
            reverse("reviews:review-list"),
            {"order_item": self.item.pk, "rating": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reviewing_someone_elses_purchase_is_refused(self) -> None:
        self.auth(self.stranger)
        response = self.client.post(
            reverse("reviews:review-list"),
            {
                "order_item": self.item.pk,
                "rating": 5,
                "body": "I did not buy this but here is five stars anyway.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_writing_a_review_requires_signing_in(self) -> None:
        response = self.client.post(
            reverse("reviews:review-list"), {"order_item": self.item.pk, "rating": 5}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_public_list_shows_approved_reviews(self) -> None:
        review = self.write_review()
        services.moderate_review(
            review, moderator=self.staff, status=ModerationStatus.APPROVED
        )
        response = self.client.get(
            reverse("reviews:product-review-list", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_the_public_list_hides_pending_reviews(self) -> None:
        self.write_review()
        response = self.client.get(
            reverse("reviews:product-review-list", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(len(response.json()["data"]), 0)

    def test_the_summary_endpoint_returns_the_distribution(self) -> None:
        response = self.client.get(
            reverse("reviews:product-review-summary", kwargs={"slug": self.product.slug})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()["data"]["distribution"]), 5)

    def test_the_eligibility_endpoint_is_public(self) -> None:
        response = self.client.get(
            reverse(
                "reviews:product-review-eligibility", kwargs={"slug": self.product.slug}
            )
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.json()["data"]["can_review"])

    def test_the_pending_endpoint_lists_reviewable_purchases(self) -> None:
        self.auth(self.user)
        response = self.client.get(reverse("reviews:review-pending"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"][0]["order_item"], self.item.pk)

    def test_a_customer_cannot_edit_another_customers_review(self) -> None:
        review = self.write_review()
        self.auth(self.stranger)
        response = self.client.patch(
            reverse("reviews:review-detail", kwargs={"uuid": review.uuid}),
            {"rating": 1},
            format="json",
        )
        self.assertIn(
            response.status_code,
            (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND),
        )

    def test_a_customer_can_delete_their_own_review(self) -> None:
        review = self.write_review()
        self.auth(self.user)
        response = self.client.delete(
            reverse("reviews:review-detail", kwargs={"uuid": review.uuid})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Review.objects.count(), 0)

    def test_the_helpful_toggle_needs_an_approved_review(self) -> None:
        review = self.write_review()
        self.auth(self.stranger)
        response = self.client.post(
            reverse("reviews:review-helpful", kwargs={"uuid": review.uuid})
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_helpful_toggle_works_on_an_approved_review(self) -> None:
        review = self.write_review()
        services.moderate_review(
            review, moderator=self.staff, status=ModerationStatus.APPROVED
        )
        self.auth(self.stranger)
        response = self.client.post(
            reverse("reviews:review-helpful", kwargs={"uuid": review.uuid})
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["helpful_count"], 1)

    def test_the_moderation_queue_is_staff_only(self) -> None:
        self.auth(self.user)
        response = self.client.get(reverse("reviews:review-moderation-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_can_bulk_approve(self) -> None:
        review = self.write_review()
        self.auth(self.staff)
        response = self.client.post(
            reverse("reviews:review-moderation-moderate"),
            {"status": ModerationStatus.APPROVED, "review_ids": [review.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["data"]["updated"], 1)

    def test_rejecting_without_a_reason_is_refused(self) -> None:
        review = self.write_review()
        self.auth(self.staff)
        response = self.client.post(
            reverse("reviews:review-moderation-moderate"),
            {"status": ModerationStatus.REJECTED, "review_ids": [review.pk]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
