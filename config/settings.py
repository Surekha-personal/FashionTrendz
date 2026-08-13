"""
Django settings for the Fashion Trendz backend.

Every environment-specific value is read from the process environment (or the
`.env` file next to `manage.py`) via python-decouple. There is deliberately no
dev/prod settings split: one module, one set of keys, behaviour switched by
`DEBUG` and overridable per-key in the environment.

Docs: https://docs.djangoproject.com/en/6.0/ref/settings/
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR: Path = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY: str = config("SECRET_KEY")
DEBUG: bool = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config("ALLOWED_HOSTS", default="", cast=Csv())
CSRF_TRUSTED_ORIGINS: list[str] = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Which deployment this process is. Reported by /status/ and stamped on log
# lines; nothing branches on it. Behaviour is switched by DEBUG and by explicit
# per-key overrides, so that a staging box misconfigured as "production" fails
# visibly rather than quietly changing what the code does.
ENVIRONMENT: str = config("ENVIRONMENT", default="development")
APP_VERSION: str = config("APP_VERSION", default="1.0.0")

ROOT_URLCONF: str = "config.urls"
WSGI_APPLICATION: str = "config.wsgi.application"
ASGI_APPLICATION: str = "config.asgi.application"
DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

# Path the Django admin is mounted at (no leading slash). Moving it off the
# default "admin/" drops the entire class of bots that probe /admin/.
ADMIN_URL: str = config("ADMIN_URL", default="admin/")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

DJANGO_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS: list[str] = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
]

# Business apps are appended here as each module is built (e.g. "apps.catalog").
LOCAL_APPS: list[str] = [
    # Core first: it owns only abstract models and shared plumbing, and every
    # other local app imports from it.
    "apps.core",
    "apps.users",
    "apps.catalog",
    "apps.products",
    "apps.wishlist",
    "apps.cart",
    "apps.orders",
    "apps.coupons",
    "apps.payments",
    "apps.reviews",
    "apps.recommendations",
    "apps.notifications",
    "apps.analytics",
    "apps.banner",
]

# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
# Each channel resolves its backend from these, so swapping the SMS stub for a
# real provider is one environment variable — no code change in the services.
NOTIFICATION_EMAIL_BACKEND: str = config(
    "NOTIFICATION_EMAIL_BACKEND",
    default="apps.notifications.channels.EmailChannel",
)
SMS_BACKEND: str = config(
    "SMS_BACKEND", default="apps.notifications.channels.ConsoleSMSChannel"
)
PUSH_BACKEND: str = config(
    "PUSH_BACKEND", default="apps.notifications.channels.ConsolePushChannel"
)

# How long a notification row is kept before the retention job removes it.
NOTIFICATION_RETENTION_DAYS: int = config(
    "NOTIFICATION_RETENTION_DAYS", default=180, cast=int
)

# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------
# Off by default: a review section that publishes before a human looks at it is
# how a product page ends up showing spam, abuse or a competitor's link. Turn on
# only for a store that accepts the risk in exchange for not staffing a queue.
REVIEW_AUTO_APPROVE: bool = config("REVIEW_AUTO_APPROVE", default=False, cast=bool)

# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
# Weights for the trending score. Documented in full in
# apps/recommendations/scoring.py — read that before changing any of them.
# Purchases outweigh views because a view is a click and a purchase is money.
TRENDING_WEIGHT_VIEW: float = config("TRENDING_WEIGHT_VIEW", default=1.0, cast=float)
TRENDING_WEIGHT_PURCHASE: float = config(
    "TRENDING_WEIGHT_PURCHASE", default=3.0, cast=float
)
TRENDING_WEIGHT_WISHLIST: float = config(
    "TRENDING_WEIGHT_WISHLIST", default=2.0, cast=float
)
TRENDING_WEIGHT_REVIEW: float = config("TRENDING_WEIGHT_REVIEW", default=1.5, cast=float)
TRENDING_WEIGHT_RATING: float = config("TRENDING_WEIGHT_RATING", default=2.0, cast=float)
TRENDING_WEIGHT_RECENCY: float = config(
    "TRENDING_WEIGHT_RECENCY", default=4.0, cast=float
)

# Days before a product's recency contribution halves.
TRENDING_HALF_LIFE_DAYS: float = config(
    "TRENDING_HALF_LIFE_DAYS", default=30.0, cast=float
)

# Reviews' worth of prior in the Bayesian rating. Higher means a product needs
# more of its own reviews before its average outranks the store mean — which is
# what stops one five-star review from topping the catalogue.
TRENDING_RATING_PRIOR: float = config(
    "TRENDING_RATING_PRIOR", default=10.0, cast=float
)

# Lifetime of a cached recommendation rail, in seconds.
RECOMMENDATION_CACHE_TTL: int = config(
    "RECOMMENDATION_CACHE_TTL", default=300, cast=int
)

# Products kept in one shopper's browsing trail. Beyond this the rail is
# scrolled past and the rows are storage that has to be cleaned up.
MAX_RECENTLY_VIEWED: int = config("MAX_RECENTLY_VIEWED", default=30, cast=int)

# ---------------------------------------------------------------------------
# Payment gateways
# ---------------------------------------------------------------------------
# Secrets, so they come from the environment and never from a committed file.
# RAZORPAY_WEBHOOK_SECRET is a *different* secret from the API key — set
# independently in the Razorpay dashboard. Using the API secret to verify
# webhooks is a silent misconfiguration: every webhook simply fails to verify.
PAYMENT_DEFAULT_GATEWAY: str = config("PAYMENT_DEFAULT_GATEWAY", default="razorpay")
RAZORPAY_KEY_ID: str = config("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET: str = config("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET: str = config("RAZORPAY_WEBHOOK_SECRET", default="")

# ---------------------------------------------------------------------------
# Cart money rules
# ---------------------------------------------------------------------------
# Read by apps/cart/services.py. Kept in settings rather than as constants so a
# festive free-shipping campaign is an environment change, not a deploy.
CART_FREE_SHIPPING_THRESHOLD: str = config("CART_FREE_SHIPPING_THRESHOLD", default="999.00")
CART_SHIPPING_CHARGE: str = config("CART_SHIPPING_CHARGE", default="79.00")
CART_PLATFORM_FEE: str = config("CART_PLATFORM_FEE", default="20.00")

# Lifetime of the cached category tree, mega menu and homepage payload.
# Invalidated on write by apps/catalog/signals.py, so this is only a backstop
# against a missed invalidation.
CATALOG_CACHE_TTL: int = config("CATALOG_CACHE_TTL", default=300, cast=int)

# Lifetime of cached product payloads (homepage rails, facets, trending
# searches). Invalidated on write by apps/products/signals.py.
PRODUCT_CACHE_TTL: int = config("PRODUCT_CACHE_TTL", default=300, cast=int)

INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Email is the login identifier; see apps/users/models.py.
AUTH_USER_MODEL: str = "users.User"

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

MIDDLEWARE: list[str] = [
    # First: everything downstream, including the logging filter, needs the id.
    "apps.core.middleware.RequestIDMiddleware",
    # Second: measures the whole stack below it, not just the view.
    "apps.core.middleware.ResponseTimeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last: closest to the view, so process_exception sees exceptions first.
    "apps.core.middleware.ExceptionLoggingMiddleware",
]

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Cache (Redis in production, in-memory otherwise)
# ---------------------------------------------------------------------------
# Every cached read in the project — catalogue payloads, rating summaries,
# recommendation rails, the analytics dashboard — goes through here.
#
# The locmem fallback is not just for convenience. Locmem is per-process, so a
# multi-worker deployment running on it caches four different answers and
# invalidates one of them; Redis is what makes cache invalidation actually
# invalidate. Set REDIS_URL in anything with more than one worker.
REDIS_URL: str = config("REDIS_URL", default="")

CACHES: dict[str, dict[str, Any]] = {
    "default": (
        {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": config("CACHE_KEY_PREFIX", default="ft"),
            "TIMEOUT": config("CACHE_DEFAULT_TIMEOUT", default=300, cast=int),
        }
        if REDIS_URL
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "fashion-trendz",
            "TIMEOUT": config("CACHE_DEFAULT_TIMEOUT", default=300, cast=int),
        }
    )
}

# Sessions in the cache when Redis is available: guest carts and browsing
# trails are keyed by session, and a database session write on every anonymous
# page view is the cheapest query to delete.
SESSION_ENGINE: str = (
    "django.contrib.sessions.backends.cache"
    if REDIS_URL
    else "django.contrib.sessions.backends.db"
)

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
# No broker configured means no queue: notifications deliver inside the request
# and scheduled jobs are run by whatever cron the host provides. That is the
# correct behaviour for development and for the test suite, where a queued task
# nobody works is indistinguishable from a bug.
CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND: str = config("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)

CELERY_TASK_SERIALIZER: str = "json"
CELERY_RESULT_SERIALIZER: str = "json"
CELERY_ACCEPT_CONTENT: list[str] = ["json"]
CELERY_TIMEZONE: str = config("TIME_ZONE", default="Asia/Kolkata")
CELERY_ENABLE_UTC: bool = True

# Run tasks inline when there is no broker, so a `.delay()` that slips into a
# code path still executes rather than vanishing.
CELERY_TASK_ALWAYS_EAGER: bool = config(
    "CELERY_TASK_ALWAYS_EAGER", default=not bool(CELERY_BROKER_URL), cast=bool
)
CELERY_TASK_EAGER_PROPAGATES: bool = True

# One task at a time per worker process. These tasks are database-bound, not
# CPU-bound, so prefetching a batch just means one slow task blocks the rest.
CELERY_WORKER_PREFETCH_MULTIPLIER: int = config(
    "CELERY_PREFETCH", default=1, cast=int
)
# Recycle workers periodically; long-lived Django processes leak connections.
CELERY_WORKER_MAX_TASKS_PER_CHILD: int = config(
    "CELERY_MAX_TASKS_PER_CHILD", default=500, cast=int
)

# Hard and soft ceilings. The soft limit raises inside the task so it can clean
# up; the hard limit kills it. Both are generous — the slowest job is the
# nightly affinity rebuild.
CELERY_TASK_SOFT_TIME_LIMIT: int = config("CELERY_SOFT_TIME_LIMIT", default=600, cast=int)
CELERY_TASK_TIME_LIMIT: int = config("CELERY_TIME_LIMIT", default=900, cast=int)

CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP: bool = True
CELERY_RESULT_EXPIRES: int = config("CELERY_RESULT_EXPIRES", default=86400, cast=int)

# ---------------------------------------------------------------------------
# Database (PostgreSQL only)
# ---------------------------------------------------------------------------

# Managed providers (Neon, Supabase, Render, Railway, Heroku) hand out a single
# DSN rather than five separate values, so DATABASE_URL wins when it is set and
# the discrete DB_* keys remain the fallback for a local or self-hosted server.
#
# Parsed with urllib rather than dj-database-url: it is fifteen lines of
# standard library against a dependency whose whole job is those fifteen lines.
DATABASE_URL: str = config("DATABASE_URL", default="")


def _database_from_url(url: str) -> dict[str, Any]:
    """Return Django database settings parsed from a PostgreSQL DSN.

    Query parameters are passed through to libpq untouched, so provider-specific
    flags such as Neon's ``channel_binding=require`` reach the driver rather
    than being silently dropped.
    """
    from urllib.parse import parse_qsl, unquote, urlparse

    parts = urlparse(url)
    options: dict[str, Any] = dict(parse_qsl(parts.query))
    options.setdefault("sslmode", "require")
    options["connect_timeout"] = config("DB_CONNECT_TIMEOUT", default=10, cast=int)

    # A "-pooler" host is PgBouncer in transaction mode. Two things break there:
    # server-side cursors, because a cursor outlives the transaction that owns
    # it; and Django's own connection reuse, which fights the external pool for
    # the same sockets. Both are switched off automatically rather than left as
    # a footgun in a runbook nobody reads.
    pooled = "-pooler" in (parts.hostname or "")

    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote((parts.path or "/").lstrip("/")),
        "USER": unquote(parts.username or ""),
        "PASSWORD": unquote(parts.password or ""),
        "HOST": parts.hostname or "localhost",
        "PORT": str(parts.port or 5432),
        # Persistent connections are pointless behind an external pooler and
        # actively harmful: they hold a pooled slot open per worker.
        "CONN_MAX_AGE": 0 if pooled else config("DB_CONN_MAX_AGE", default=60, cast=int),
        "CONN_HEALTH_CHECKS": not pooled,
        "DISABLE_SERVER_SIDE_CURSORS": pooled,
        "OPTIONS": options,
    }


DATABASES: dict[str, dict[str, Any]] = {
    "default": _database_from_url(DATABASE_URL) if DATABASE_URL else {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
        # Persistent connections: reuse sockets between requests instead of
        # paying the Postgres handshake on every API call.
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=60, cast=int),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "connect_timeout": config("DB_CONNECT_TIMEOUT", default=10, cast=int),
            "sslmode": config("DB_SSLMODE", default="prefer"),
        },
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS: list[dict[str, Any]] = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": config("PASSWORD_MIN_LENGTH", default=8, cast=int)},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE: str = config("LANGUAGE_CODE", default="en-us")
TIME_ZONE: str = config("TIME_ZONE", default="UTC")
USE_I18N: bool = True
USE_TZ: bool = True

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------

STATIC_URL: str = "/static/"
STATIC_ROOT: Path = BASE_DIR / "staticfiles"
STATICFILES_DIRS: list[Path] = [BASE_DIR / "static"]

MEDIA_URL: str = "/media/"
MEDIA_ROOT: Path = BASE_DIR / "media"

# Object storage. Django 4.2+ resolves the default file storage from this dict,
# so pointing media at S3, Spaces or R2 is a settings change and nothing else —
# no model field, no upload path and no view is aware of where files land.
#
# S3 is only wired in when a bucket is named. A half-configured bucket that
# silently falls back to local disk would spread a deployment's media across
# two places, which is worse than not using S3 at all.
AWS_STORAGE_BUCKET_NAME: str = config("AWS_STORAGE_BUCKET_NAME", default="")
AWS_ACCESS_KEY_ID: str = config("AWS_ACCESS_KEY_ID", default="")
AWS_SECRET_ACCESS_KEY: str = config("AWS_SECRET_ACCESS_KEY", default="")
AWS_S3_REGION_NAME: str = config("AWS_S3_REGION_NAME", default="ap-south-1")
AWS_S3_ENDPOINT_URL: str = config("AWS_S3_ENDPOINT_URL", default="") or None
AWS_S3_CUSTOM_DOMAIN: str = config("AWS_S3_CUSTOM_DOMAIN", default="")
# Product imagery is public and immutable once uploaded; a year of browser
# caching is the single biggest win available on a catalogue page.
AWS_S3_OBJECT_PARAMETERS: dict[str, str] = {"CacheControl": "max-age=31536000"}
AWS_DEFAULT_ACL: str | None = None
AWS_QUERYSTRING_AUTH: bool = False

STORAGES: dict[str, dict[str, Any]] = {
    "default": (
        {"BACKEND": "storages.backends.s3.S3Storage"}
        if AWS_STORAGE_BUCKET_NAME
        else {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    ),
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

# Upload ceilings — product imagery is the only large payload this API accepts.
DATA_UPLOAD_MAX_MEMORY_SIZE: int = config(
    "DATA_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024, cast=int
)
FILE_UPLOAD_MAX_MEMORY_SIZE: int = config(
    "FILE_UPLOAD_MAX_MEMORY_SIZE", default=5 * 1024 * 1024, cast=int
)
DATA_UPLOAD_MAX_NUMBER_FIELDS: int = config(
    "DATA_UPLOAD_MAX_NUMBER_FIELDS", default=1000, cast=int
)

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Closed by default: an endpoint that should be public opts in with an
    # explicit AllowAny. A forgotten permission_classes then fails safe.
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": config("API_PAGE_SIZE", default=20, cast=int),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Every failure — serializer, permission, 404, IntegrityError, unhandled
    # bug — leaves the process in the standard envelope. See apps/core/exceptions.py.
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # The envelope renderer replaces JSONRenderer globally, so third-party
    # views (SimpleJWT's token endpoints) are wrapped too, with no subclassing.
    "DEFAULT_RENDERER_CLASSES": (
        (
            "apps.core.responses.EnvelopeJSONRenderer",
            "rest_framework.renderers.BrowsableAPIRenderer",
        )
        if DEBUG
        else ("apps.core.responses.EnvelopeJSONRenderer",)
    ),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": config("THROTTLE_ANON", default="100/hour"),
        "user": config("THROTTLE_USER", default="1000/hour"),
        # Scoped rates for credential endpoints. These are the endpoints worth
        # brute-forcing, so they get far tighter limits than the global anon rate.
        "login": config("THROTTLE_LOGIN", default="10/min"),
        "register": config("THROTTLE_REGISTER", default="10/hour"),
        "password_reset": config("THROTTLE_PASSWORD_RESET", default="5/hour"),
        # Keyed by user, not IP: shoppers behind carrier-grade NAT share an
        # address and must not throttle each other out of checking out.
        "checkout": config("THROTTLE_CHECKOUT", default="30/hour"),
        # Short-window companion limit; see apps.core.throttling.BurstThrottle.
        "burst": config("THROTTLE_BURST", default="60/min"),
        # Analytics and reports aggregate the whole orders table. Staff-only,
        # so the limit is not about abuse — it is about one admin holding a
        # refresh key and taking the database down for everyone else.
        "analytics": config("THROTTLE_ANALYTICS", default="120/hour"),
        # A CSV export can walk five thousand orders. Tighter than analytics
        # for the same reason, one order of magnitude further along.
        "report": config("THROTTLE_REPORT", default="30/hour"),
        # Draining or retrying the notification queue actually sends mail.
        "notification_queue": config("THROTTLE_NOTIFICATION_QUEUE", default="20/hour"),
        # Recording a product view is fire-and-forget from the product page and
        # fires on every navigation, so it needs headroom the global user rate
        # does not give it.
        "product_view": config("THROTTLE_PRODUCT_VIEW", default="600/hour"),
    },
    "DATETIME_FORMAT": "iso-8601",
    "COERCE_DECIMAL_TO_STRING": True,
}

# ---------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt)
# ---------------------------------------------------------------------------

SIMPLE_JWT: dict[str, Any] = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": config(
        "JWT_ROTATE_REFRESH_TOKENS", default=True, cast=bool
    ),
    "BLACKLIST_AFTER_ROTATION": config(
        "JWT_BLACKLIST_AFTER_ROTATION", default=True, cast=bool
    ),
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": config("JWT_ALGORITHM", default="HS256"),
    "SIGNING_KEY": config("JWT_SIGNING_KEY", default=SECRET_KEY),
    "VERIFYING_KEY": "",
    "AUDIENCE": config("JWT_AUDIENCE", default=None),
    "ISSUER": config("JWT_ISSUER", default=None),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "LEEWAY": config("JWT_LEEWAY_SECONDS", default=0, cast=int),
}

# ---------------------------------------------------------------------------
# OpenAPI / drf-spectacular
# ---------------------------------------------------------------------------

# Swagger/ReDoc/schema routes are registered only when this is on. Leave it on
# for a public API; turn it off to hide the surface map of a private one.
ENABLE_API_DOCS: bool = config("ENABLE_API_DOCS", default=True, cast=bool)

SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": config("API_TITLE", default="Fashion Trendz API"),
    "DESCRIPTION": config(
        "API_DESCRIPTION",
        default="REST API powering the Fashion Trendz storefront.",
    ),
    "VERSION": config("API_VERSION", default="1.0.0"),
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    "SWAGGER_UI_SETTINGS": {
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
    },
    "REDOC_UI_SETTINGS": {
        "hideDownloadButton": False,
    },
    "SERVERS": [{"url": config("API_SERVER_URL", default="http://127.0.0.1:8000")}],
}

# ---------------------------------------------------------------------------
# CORS (Next.js frontend)
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS: list[str] = config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())
CORS_ALLOW_CREDENTIALS: bool = config("CORS_ALLOW_CREDENTIALS", default=True, cast=bool)
CORS_ALLOW_HEADERS: list[str] = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    # Guest identity for the cart and the browsing trail. Sent by the Next.js
    # client on every cart and recently-viewed call; without it here the
    # browser fails the preflight and a signed-out shopper silently loses
    # their bag.
    "x-cart-session",
]
CORS_ALLOW_METHODS: list[str] = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
# Only API and media routes are cross-origin; the admin never is.
CORS_URLS_REGEX: str = r"^/(api|media)/.*$"

# ---------------------------------------------------------------------------
# Email & password reset
# ---------------------------------------------------------------------------

# Console backend prints emails to stdout, so the reset flow is fully testable
# locally without SMTP credentials. Set EMAIL_BACKEND to the SMTP backend in
# any environment that must actually deliver mail.
EMAIL_BACKEND: str = config(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    ),
)
EMAIL_HOST: str = config("EMAIL_HOST", default="")
EMAIL_PORT: int = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER: str = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD: str = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS: bool = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_TIMEOUT: int = config("EMAIL_TIMEOUT", default=10, cast=int)
DEFAULT_FROM_EMAIL: str = config(
    "DEFAULT_FROM_EMAIL", default="Fashion Trendz <no-reply@fashiontrendz.local>"
)

# Lifetime of a password reset link, in seconds (Django default is 3 days).
PASSWORD_RESET_TIMEOUT: int = config(
    "PASSWORD_RESET_TIMEOUT", default=60 * 60 * 24, cast=int
)

# The reset link points at the Next.js frontend, not at this API — the user
# needs a form, and the frontend POSTs the uid/token back to /reset-password/.
FRONTEND_URL: str = config("FRONTEND_URL", default="http://localhost:3000")
PASSWORD_RESET_URL_TEMPLATE: str = config(
    "PASSWORD_RESET_URL_TEMPLATE",
    default=f"{FRONTEND_URL}/reset-password?uid={{uid}}&token={{token}}",
)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SECURE: bool = not DEBUG

SECURE_SSL_REDIRECT: bool = config("SECURE_SSL_REDIRECT", default=_SECURE, cast=bool)
SECURE_HSTS_SECONDS: int = config(
    "SECURE_HSTS_SECONDS", default=31536000 if _SECURE else 0, cast=int
)
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=_SECURE, cast=bool
)
SECURE_HSTS_PRELOAD: bool = config("SECURE_HSTS_PRELOAD", default=_SECURE, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF: bool = True
SECURE_REFERRER_POLICY: str = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY: str = "same-origin"
X_FRAME_OPTIONS: str = "DENY"

SESSION_COOKIE_SECURE: bool = config("SESSION_COOKIE_SECURE", default=_SECURE, cast=bool)
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = config("SESSION_COOKIE_SAMESITE", default="Lax")
CSRF_COOKIE_SECURE: bool = config("CSRF_COOKIE_SECURE", default=_SECURE, cast=bool)
CSRF_COOKIE_SAMESITE: str = config("CSRF_COOKIE_SAMESITE", default="Lax")

# Behind a TLS-terminating proxy (Render, Railway, nginx, ALB) Django only sees
# plain HTTP; without this header mapping SECURE_SSL_REDIRECT redirect-loops.
if config("USE_X_FORWARDED_PROTO", default=_SECURE, cast=bool):
    SECURE_PROXY_SSL_HEADER: tuple[str, str] = ("HTTP_X_FORWARDED_PROTO", "https")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL: str = config("LOG_LEVEL", default="INFO").upper()

# ponytail: stdout only — every target platform (Docker, Render, Railway,
# systemd, gunicorn) already captures and rotates stdout. Add a RotatingFileHandler
# only if the app is ever run somewhere that does not.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        # Stamps every record with the current request's id. Registered as a
        # filter rather than relying on the formatter, because a formatter
        # referencing a missing attribute raises KeyError on startup records.
        "request_id": {
            "()": "apps.core.logging.RequestIDFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": (
                "{asctime} {levelname} {name} {process:d} "
                "[req:{request_id}] {message}"
            ),
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "level": config("SQL_LOG_LEVEL", default="WARNING").upper(),
            "propagate": False,
        },
        # Application loggers. "apps" is the parent of every module logger
        # (apps.core.*, apps.users.*), so one entry configures them all.
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Per-request access log emitted by ResponseTimeMiddleware. Split out
        # so it can be silenced independently of application logging, which is
        # the first thing anyone wants when reading a noisy local console.
        "apps.api": {
            "handlers": ["console"],
            "level": config("API_LOG_LEVEL", default="INFO").upper(),
            "propagate": False,
        },
    },
}
