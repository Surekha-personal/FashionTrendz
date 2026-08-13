"""Monitoring routes.

Mounted at the project root rather than under ``/api/v1/``: a health check is
not part of the versioned API contract, and orchestrators expect it at a stable
path that survives the next version bump.
"""

from __future__ import annotations

from django.urls import URLPattern, path

from apps.core.views import (
    ApplicationStatusAPIView,
    HealthCheckAPIView,
    ReadinessAPIView,
    SystemInformationAPIView,
)

app_name = "core"

urlpatterns: list[URLPattern] = [
    path("health/", HealthCheckAPIView.as_view(), name="health"),
    path("ready/", ReadinessAPIView.as_view(), name="ready"),
    path("status/", ApplicationStatusAPIView.as_view(), name="status"),
    path("system/", SystemInformationAPIView.as_view(), name="system"),
]
