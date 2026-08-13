"""Manager for the email-authenticated custom user model."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.users.models import User


class UserManager(BaseUserManager):
    """Creates users keyed on email instead of Django's default username.

    ``createsuperuser`` and every ``User.objects.create_user`` call route
    through here, so email normalisation and the staff/superuser invariants
    are enforced in exactly one place.
    """

    use_in_migrations = True

    def get_by_natural_key(self, username: str | None) -> "User":
        """Look up an account by email, case-insensitively.

        ``ModelBackend.authenticate`` funnels every login through this method.
        Without the fold, a user who registered as "Shopper@Example.com" (stored
        lowercased by ``User.save``) could not log in with the exact string they
        typed at signup. Lowercasing rather than using ``__iexact`` keeps the
        lookup on the unique btree index instead of forcing a sequential scan.
        """
        return self.get(**{self.model.USERNAME_FIELD: (username or "").lower()})

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields: Any,
    ) -> "User":
        """Shared construction path for regular users and superusers."""
        if not email:
            raise ValueError(_("An email address is required."))

        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)

        if password:
            # set_password hashes with the configured hasher; assigning to
            # user.password directly would store the plaintext.
            user.set_password(password)
        else:
            # Unusable password: the account exists but cannot be logged into
            # with credentials until a password is set via the reset flow.
            user.set_unusable_password()

        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        """Create a standard, non-privileged account."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(
        self,
        email: str,
        password: str | None = None,
        **extra_fields: Any,
    ) -> "User":
        """Create an account with full admin privileges."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_email_verified", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)
