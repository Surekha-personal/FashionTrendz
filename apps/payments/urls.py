"""URL routes for the payments module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter

from apps.payments.views import PaymentViewSet, RefundViewSet, WebhookViewSet

app_name = "payments"

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payment")
router.register("payments/webhook", WebhookViewSet, basename="payment-webhook")
router.register("refunds", RefundViewSet, basename="refund")

urlpatterns: list[URLPattern | URLResolver] = [
    path("", include(router.urls)),
]
