"""Django admin for reviews — a working moderation console."""

from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.reviews import services
from apps.reviews.models import HelpfulVote, ModerationStatus, Review, ReviewImage


class ReviewImageInline(admin.TabularInline):
    """Photographs attached to the review being moderated.

    Read-only and inline because the photo is usually *why* a review is held —
    a moderator who has to open another page to see it will approve blind.
    """

    model = ReviewImage
    extra = 0
    fields = ("preview", "caption", "display_order")
    readonly_fields = ("preview",)

    @admin.display(description=_("preview"))
    def preview(self, obj: ReviewImage) -> str:
        """Render a thumbnail of the customer's photograph."""
        source = obj.thumbnail or obj.image
        if not source:
            return "—"
        return format_html(
            '<img src="{}" style="max-height:120px;border-radius:4px;" />', source.url
        )


class HasImagesFilter(admin.SimpleListFilter):
    """Filter the queue down to reviews carrying photographs."""

    title = _("photos")
    parameter_name = "has_images"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        """Return the two useful options."""
        return [("yes", _("With photos")), ("no", _("Without photos"))]

    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet:
        """Apply the chosen option."""
        if self.value() == "yes":
            return queryset.with_images()
        if self.value() == "no":
            return queryset.exclude(pk__in=queryset.with_images().values("pk"))
        return queryset


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """The moderation console."""

    list_display = (
        "id",
        "product_link",
        "rating_stars",
        "short_body",
        "user",
        "is_verified_purchase",
        "status",
        "helpful_count",
        "created_at",
    )
    list_filter = (
        "status",
        "rating",
        "is_verified_purchase",
        HasImagesFilter,
        "created_at",
    )
    search_fields = (
        "title",
        "body",
        "user__email",
        "product__name",
        "product__slug",
    )
    # Raw ids on purpose: the product and user selects would otherwise render
    # every row in a catalogue of hundreds of products and thousands of users.
    raw_id_fields = ("product", "user", "order_item", "moderated_by")
    readonly_fields = (
        "uuid",
        "helpful_count",
        "is_verified_purchase",
        "moderated_by",
        "moderated_at",
        "created_at",
        "updated_at",
    )
    inlines = [ReviewImageInline]
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    actions = ("approve_selected", "reject_selected", "recount_helpful_votes")

    fieldsets = (
        (None, {"fields": ("uuid", "product", "user", "order_item")}),
        (_("Review"), {"fields": ("rating", "title", "body")}),
        (
            _("Moderation"),
            {
                "fields": (
                    "status",
                    "rejection_reason",
                    "moderated_by",
                    "moderated_at",
                    "is_verified_purchase",
                )
            },
        ),
        (_("Engagement"), {"fields": ("helpful_count",)}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    def get_queryset(self, request: HttpRequest) -> QuerySet[Review]:
        """Join the columns the changelist renders, so the page is one query."""
        return super().get_queryset(request).select_related("product", "user")

    @admin.display(description=_("product"), ordering="product__name")
    def product_link(self, obj: Review) -> str:
        """Link through to the reviewed product."""
        return format_html(
            '<a href="/admin/products/product/{}/change/">{}</a>',
            obj.product_id,
            obj.product.name,
        )

    @admin.display(description=_("rating"), ordering="rating")
    def rating_stars(self, obj: Review) -> str:
        """Render the rating as stars — scannable at a glance down a column."""
        return "★" * obj.rating + "☆" * (5 - obj.rating)

    @admin.display(description=_("review"))
    def short_body(self, obj: Review) -> str:
        """Truncate the body so one review is one row."""
        text = obj.title or obj.body
        return (text[:70] + "…") if len(text) > 70 else (text or "—")

    @admin.action(description=_("Approve selected reviews"))
    def approve_selected(self, request: HttpRequest, queryset: QuerySet[Review]) -> None:
        """Publish the selected reviews and refresh affected ratings."""
        count = services.bulk_moderate(
            queryset, moderator=request.user, status=ModerationStatus.APPROVED
        )
        self.message_user(request, f"{count} review(s) approved.", messages.SUCCESS)

    @admin.action(description=_("Reject selected reviews"))
    def reject_selected(self, request: HttpRequest, queryset: QuerySet[Review]) -> None:
        """Reject the selected reviews with a generic reason.

        A per-review reason needs an intermediate form; the bulk action is for
        clearing obvious spam, where the reason is always the same.
        """
        count = services.bulk_moderate(
            queryset,
            moderator=request.user,
            status=ModerationStatus.REJECTED,
            reason="Does not meet our review guidelines.",
        )
        self.message_user(request, f"{count} review(s) rejected.", messages.WARNING)

    @admin.action(description=_("Recount helpful votes"))
    def recount_helpful_votes(
        self, request: HttpRequest, queryset: QuerySet[Review]
    ) -> None:
        """Rebuild the denormalised counter from the vote rows."""
        for review in queryset:
            services.recount_helpful(review)
        self.message_user(request, "Helpful counts rebuilt.", messages.SUCCESS)


@admin.register(ReviewImage)
class ReviewImageAdmin(admin.ModelAdmin):
    """Customer photographs, searchable independently of their review."""

    list_display = ("id", "review", "caption", "display_order", "created_at")
    list_filter = ("created_at",)
    search_fields = ("caption", "review__product__name")
    raw_id_fields = ("review",)
    readonly_fields = ("uuid", "created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[ReviewImage]:
        """Join the review shown in the changelist."""
        return super().get_queryset(request).select_related("review", "review__product")


@admin.register(HelpfulVote)
class HelpfulVoteAdmin(admin.ModelAdmin):
    """Vote rows, exposed for auditing a suspicious helpful_count."""

    list_display = ("id", "review", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__email",)
    raw_id_fields = ("review", "user")
    readonly_fields = ("uuid", "created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> QuerySet[HelpfulVote]:
        """Join the columns the changelist renders."""
        return super().get_queryset(request).select_related("review", "user")
