"""URL routes for the reviews module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.reviews.views import (
    ProductReviewViewSet,
    ReviewModerationViewSet,
    ReviewViewSet,
)

app_name = "reviews"

router = DefaultRouter()
router.register("reviews", ReviewViewSet, basename="review")
router.register("admin/reviews", ReviewModerationViewSet, basename="review-moderation")

# The per-product routes carry the slug in the path, which a router prefix
# cannot express, so they are registered on their own router and included under
# an explicit prefix rather than bent into the flat one above.
product_router = DefaultRouter()
product_router.register("", ProductReviewViewSet, basename="product-review")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
    path("products/<slug:slug>/reviews/", include(product_router.urls)),
]
