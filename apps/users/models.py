"""User and Address models for the Fashion Trendz storefront."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.users.managers import UserManager
from apps.users.validators import (
    mobile_number_validator,
    validate_date_of_birth,
    validate_profile_image,
)


def profile_image_upload_to(instance: "User", filename: str) -> str:
    """Return a collision-proof storage path for a profile image.

    Must stay a module-level function: migrations serialise a reference to it,
    and a lambda or bound method cannot be serialised.
    """
    suffix = Path(filename).suffix.lower()
    return f"users/profile/{uuid.uuid4().hex}{suffix}"


class User(AbstractBaseUser, PermissionsMixin):
    """Storefront account, authenticated by email address.

    Extends ``AbstractBaseUser`` rather than ``AbstractUser`` because the
    latter carries a mandatory ``username`` column that this project has no
    use for and could not cleanly drop later.
    """

    class Gender(models.TextChoices):
        MALE = "male", _("Male")
        FEMALE = "female", _("Female")
        OTHER = "other", _("Other")
        UNDISCLOSED = "undisclosed", _("Prefer not to say")

    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    email = models.EmailField(_("email address"), unique=True)
    mobile_number = models.CharField(
        _("mobile number"),
        max_length=16,
        blank=True,
        validators=[mobile_number_validator],
    )
    profile_image = models.ImageField(
        _("profile image"),
        upload_to=profile_image_upload_to,
        blank=True,
        null=True,
        validators=[validate_profile_image],
    )
    date_of_birth = models.DateField(
        _("date of birth"),
        blank=True,
        null=True,
        validators=[validate_date_of_birth],
    )
    gender = models.CharField(
        _("gender"),
        max_length=12,
        choices=Gender.choices,
        blank=True,
    )

    is_email_verified = models.BooleanField(_("email verified"), default=False)
    is_mobile_verified = models.BooleanField(_("mobile verified"), default=False)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Unselect this instead of deleting accounts."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into the admin site."),
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"], name="user_created_at_idx"),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Normalise the email before every write.

        Case-folding here rather than in a serializer guarantees the uniqueness
        constraint is meaningful no matter which code path created the row —
        API, admin, management command or shell.
        """
        if self.email:
            self.email = self.__class__.objects.normalize_email(self.email).lower()
        super().save(*args, **kwargs)

    def get_full_name(self) -> str:
        """Return first and last name joined, collapsing the empty last name."""
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        """Return the name used in greetings."""
        return self.first_name

    @property
    def default_address(self) -> "Address | None":
        """Return this user's default shipping address, if one is set."""
        return self.addresses.filter(is_default=True).first()


class Address(models.Model):
    """A shipping or billing address belonging to a single user."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("user"),
    )
    full_name = models.CharField(_("full name"), max_length=150)
    mobile = models.CharField(
        _("mobile"),
        max_length=16,
        validators=[mobile_number_validator],
    )
    address_line_1 = models.CharField(_("address line 1"), max_length=255)
    address_line_2 = models.CharField(_("address line 2"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100)
    state = models.CharField(_("state"), max_length=100)
    country = models.CharField(_("country"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=16)
    is_default = models.BooleanField(_("default address"), default=False)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        # Default first, then newest — the order the checkout page wants.
        ordering = ["-is_default", "-created_at"]
        constraints = [
            # Partial unique index: enforces "at most one default per user" in
            # the database itself, so a race between two concurrent requests
            # cannot leave a user with two defaults.
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_default=True),
                name="unique_default_address_per_user",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_default"], name="address_user_default_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name}, {self.city} ({self.user.email})"

    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> None:
        """Maintain the single-default invariant around every write.

        The demotion must happen *before* this row is written, otherwise the
        partial unique index rejects the insert while the old default still
        holds the slot.
        """
        siblings = Address.objects.filter(user_id=self.user_id)

        # A user's first address is their default; there is nothing to choose.
        if self._state.adding and not siblings.exists():
            self.is_default = True

        if self.is_default:
            demote = siblings.filter(is_default=True)
            if self.pk is not None:
                demote = demote.exclude(pk=self.pk)
            demote.update(is_default=False)

        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        """Promote the next-newest address when the default is removed."""
        was_default = self.is_default
        user_id = self.user_id
        result = super().delete(*args, **kwargs)

        if was_default:
            successor = Address.objects.filter(user_id=user_id).first()
            if successor is not None:
                successor.is_default = True
                successor.save(update_fields=["is_default", "updated_at"])

        return result
