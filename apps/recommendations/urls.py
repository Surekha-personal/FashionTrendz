"""URL routes for the recommendations module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.recommendations.views import (
    RecentlyViewedViewSet,
    RecommendationAdminViewSet,
    RecommendationViewSet,
)

app_name = "recommendations"

router = DefaultRouter()
router.register("recently-viewed", RecentlyViewedViewSet, basename="recently-viewed")
router.register("recommendations", RecommendationViewSet, basename="recommendation")
router.register(
    "admin/recommendations", RecommendationAdminViewSet, basename="recommendation-admin"
)

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
