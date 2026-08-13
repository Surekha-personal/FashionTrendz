"""URL routes for the analytics module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.analytics.views import AnalyticsViewSet, DashboardViewSet, ReportViewSet

app_name = "analytics"

router = DefaultRouter()
router.register("admin/dashboard", DashboardViewSet, basename="dashboard")
router.register("admin/analytics", AnalyticsViewSet, basename="analytics")
router.register("admin/reports", ReportViewSet, basename="report")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
