"""Querysets and managers for the coupons module."""

from __future__ import annotations

from django.db import models
from django.db.models import Count, F, Q
from django.utils import timezone


class CouponQuerySet(models.QuerySet):
    """Queries over coupons."""

    def active(self) -> "CouponQuerySet":
        """Restrict to coupons the merchandiser has switched on."""
        return self.filter(is_active=True)

    def current(self) -> "CouponQuerySet":
        """Restrict to coupons inside their validity window.

        A null ``valid_until`` means "no end date", which is how an evergreen
        first-order coupon is expressed. Comparing in SQL rather than Python is
        what lets a campaign start and stop on schedule with nobody deploying.
        """
        now = timezone.now()
        return self.filter(valid_from__lte=now).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now)
        )

    def not_exhausted(self) -> "CouponQuerySet":
        """Restrict to coupons with redemptions left.

        ``max_uses = 0`` means unlimited, which is the natural default for a
        code with no cap rather than a sentinel nobody remembers.
        """
        return self.filter(Q(max_uses=0) | Q(times_used__lt=F("max_uses")))

    def redeemable(self) -> "CouponQuerySet":
        """Restrict to coupons a customer could actually use right now."""
        return self.active().current().not_exhausted()

    def public(self) -> "CouponQuerySet":
        """Restrict to coupons advertised on the storefront.

        Private codes — influencer links, support goodwill gestures — are
        redeemable but must never appear in the "available offers" list.
        """
        return self.redeemable().filter(is_public=True)

    def expired(self) -> "CouponQuerySet":
        """Restrict to coupons past their end date."""
        return self.filter(valid_until__isnull=False, valid_until__lt=timezone.now())

    def with_usage(self) -> "CouponQuerySet":
        """Annotate the real redemption count from the usage table."""
        return self.annotate(_usage_count=Count("usages", distinct=True))

    def with_restrictions(self) -> "CouponQuerySet":
        """Prefetch the restriction relations the validator reads."""
        return self.prefetch_related("categories", "brands", "products")


class CouponUsageQuerySet(models.QuerySet):
    """Queries over coupon redemptions."""

    def for_user(self, user: models.Model) -> "CouponUsageQuerySet":
        """Restrict to one customer's redemptions."""
        return self.filter(user=user)

    def counted(self) -> "CouponUsageQuerySet":
        """Restrict to redemptions that still count against the limits.

        A cancelled order gives its redemption back — otherwise a customer who
        cancels has silently burned their one allowed use, which is the kind of
        thing that generates a support ticket the agent cannot resolve.
        """
        return self.filter(is_released=False)


CouponManager = models.Manager.from_queryset(CouponQuerySet)
CouponUsageManager = models.Manager.from_queryset(CouponUsageQuerySet)
