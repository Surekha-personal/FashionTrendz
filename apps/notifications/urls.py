"""URL routes for the notifications module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import NotificationAdminViewSet, NotificationViewSet

app_name = "notifications"

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register(
    "admin/notifications", NotificationAdminViewSet, basename="notification-admin"
)

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
