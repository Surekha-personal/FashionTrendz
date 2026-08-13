"""Named throttle classes.

Each class binds a fixed scope, so a view declares intent in one line::

    class CheckoutAPIView(GenericAPIView):
        throttle_classes = [CheckoutThrottle]

rather than the two-line ``ScopedRateThrottle`` plus ``throttle_scope`` pair.
The rates themselves stay in ``settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]``,
sourced from environment variables — so limits are tuned per environment
without a code change.

The scope names deliberately match those already used by the Module 2 auth
views, so both share one counter per client rather than granting two budgets
for the same endpoint.
"""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request
from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)
from rest_framework.views import APIView


class IPRateThrottle(SimpleRateThrottle):
    """Throttle by client IP regardless of authentication state.

    The right key for credential endpoints. ``UserRateThrottle`` falls back to
    the IP only when anonymous, so an attacker who can create accounts gets a
    fresh budget per account. Keying on IP unconditionally means login attempts
    from one source share one counter whoever they claim to be.
    """

    scope = "anon"

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        """Return a cache key derived from the client address."""
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class AnonymousThrottle(AnonRateThrottle):
    """Global ceiling for unauthenticated traffic. Scope: ``anon``."""

    scope = "anon"


class AuthenticatedThrottle(UserRateThrottle):
    """Global ceiling for signed-in traffic. Scope: ``user``."""

    scope = "user"


class LoginThrottle(IPRateThrottle):
    """Rate limit for the login endpoint. Scope: ``login``.

    The tightest limit in the project, because this is the endpoint worth
    brute-forcing. Keyed by IP so guessing many passwords against one account,
    or one password against many accounts, both hit the same counter.
    """

    scope = "login"


class RegisterThrottle(IPRateThrottle):
    """Rate limit for account creation. Scope: ``register``.

    Caps automated signup floods, which otherwise fill the user table with junk
    and burn the outbound email reputation that real customers depend on.
    """

    scope = "register"


class PasswordResetThrottle(IPRateThrottle):
    """Rate limit for forgot-password and reset-password. Scope: ``password_reset``.

    Each accepted call sends an email. Without a limit this endpoint is a free
    way to mail-bomb any known address, using this domain's sending reputation.
    """

    scope = "password_reset"


class CheckoutThrottle(UserRateThrottle):
    """Rate limit for order placement and payment initiation. Scope: ``checkout``.

    Keyed by user, not IP: shoppers on shared or carrier-grade NAT connections
    legitimately share an address, and blocking one because a neighbour is
    buying is worse than the abuse it prevents.

    A modest per-user ceiling still stops the double-submit storm that a
    frustrated customer produces by clicking "Place order" repeatedly.
    """

    scope = "checkout"


class BurstThrottle(UserRateThrottle):
    """Short-window ceiling. Scope: ``burst``.

    Pair with :class:`AuthenticatedThrottle` when an endpoint needs both a
    per-minute burst limit and a per-hour sustained limit::

        throttle_classes = [BurstThrottle, AuthenticatedThrottle]

    DRF applies every class in the list, so the strictest one wins.
    """

    scope = "burst"


class AnalyticsThrottle(UserRateThrottle):
    """Rate limit for admin analytics reads. Scope: ``analytics``.

    Not an abuse control — these endpoints are staff-only. It is a protection
    against one admin holding the refresh key on a dashboard that aggregates
    the whole orders table, and taking the database down for the storefront.
    """

    scope = "analytics"


class ReportThrottle(UserRateThrottle):
    """Rate limit for CSV exports. Scope: ``report``.

    Tighter than :class:`AnalyticsThrottle`: a report walks thousands of order
    rows and serialises every one of them.
    """

    scope = "report"


class NotificationQueueThrottle(UserRateThrottle):
    """Rate limit for manual queue operations. Scope: ``notification_queue``.

    These two endpoints send real mail. A repeated click on "retry" against a
    large backlog is customer-visible, and unlike most mistakes in an admin it
    cannot be undone.
    """

    scope = "notification_queue"


class ProductViewThrottle(UserRateThrottle):
    """Rate limit for recording browsing history. Scope: ``product_view``.

    Deliberately generous. The product page fires this on every navigation, so
    a shopper browsing normally would hit the standard user rate within an hour
    and start losing their own browsing trail.
    """

    scope = "product_view"

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        """Key by user when signed in, by session or IP when not.

        The endpoint accepts guests, and ``UserRateThrottle`` falls back to the
        IP address for them — which would throttle an entire office network as
        one shopper.
        """
        if request.user and request.user.is_authenticated:
            ident = str(request.user.pk)
        else:
            ident = request.META.get("HTTP_X_CART_SESSION") or self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


def scoped_throttle(scope_name: str) -> type[SimpleRateThrottle]:
    """Build an IP-keyed throttle class for an ad-hoc scope.

    For one-off endpoints that need their own budget without a permanent class
    here. The scope must have a matching entry in ``DEFAULT_THROTTLE_RATES``,
    or DRF raises at startup::

        throttle_classes = [scoped_throttle("coupon_validate")]
    """
    return type(
        f"{scope_name.title().replace('_', '')}Throttle",
        (IPRateThrottle,),
        {"scope": scope_name, "__doc__": f"Ad-hoc throttle for scope {scope_name!r}."},
    )


def throttle_status(request: Request, *throttles: Any) -> dict[str, Any]:
    """Return remaining allowance per throttle, for a debug or status endpoint."""
    report: dict[str, Any] = {}
    for throttle in throttles:
        instance = throttle() if isinstance(throttle, type) else throttle
        key = instance.get_cache_key(request, None)
        history = instance.cache.get(key, []) if key else []
        report[instance.scope] = {
            "limit": instance.num_requests,
            "used": len(history),
            "remaining": max(instance.num_requests - len(history), 0),
        }
    return report
