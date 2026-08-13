"""
Root URL configuration for the Fashion Trendz backend.

Layout:
    <ADMIN_URL>          Django admin (path is env-configurable)
    /api/v1/             versioned API surface; each module appends its include
    /api/schema/         raw OpenAPI 3 document
    /api/docs/           Swagger UI
    /api/redoc/          ReDoc

Docs: https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

urlpatterns: list[URLPattern | URLResolver] = [
    path(settings.ADMIN_URL, admin.site.urls),
]

# Versioned API routes. Each module built from here on appends its own
# path("api/v1/<resource>/", include("apps.<module>.urls")) entry.
api_v1_patterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include("apps.users.urls", namespace="users")),
    path("api/v1/", include("apps.catalog.urls", namespace="catalog")),
    path("api/v1/", include("apps.products.urls", namespace="products")),
    path("api/v1/", include("apps.wishlist.urls", namespace="wishlist")),
    path("api/v1/", include("apps.cart.urls", namespace="cart")),
    path("api/v1/", include("apps.orders.urls", namespace="orders")),
    path("api/v1/", include("apps.coupons.urls", namespace="coupons")),
    path("api/v1/", include("apps.payments.urls", namespace="payments")),
    path("api/v1/", include("apps.reviews.urls", namespace="reviews")),
    path("api/v1/", include("apps.recommendations.urls", namespace="recommendations")),
    path("api/v1/", include("apps.notifications.urls", namespace="notifications")),
    path("api/v1/", include("apps.analytics.urls", namespace="analytics")),
    path("api/v1/", include("apps.banner.urls", namespace="banner")),
]

# Monitoring sits at the root, outside the versioned API. Load balancers and
# orchestrators poll a fixed path and must not have to follow an API version
# bump to keep probing.
urlpatterns += [path("", include("apps.core.urls", namespace="core"))]

urlpatterns += api_v1_patterns

if settings.ENABLE_API_DOCS:
    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path(
            "api/docs/",
            SpectacularSwaggerView.as_view(url_name="schema"),
            name="swagger-ui",
        ),
        path(
            "api/redoc/",
            SpectacularRedocView.as_view(url_name="schema"),
            name="redoc",
        ),
    ]

if settings.DEBUG:
    # Development convenience only. In production, uploaded media is served by
    # the reverse proxy or object storage, never by Django.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
