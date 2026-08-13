"""Tests for the users module.

Covers the manager invariants, every authentication endpoint, profile access
control, the address default-selection rules and the field validators.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import Address, User
from apps.users.serializers import build_password_reset_payload
from apps.users.validators import validate_date_of_birth

STRONG_PASSWORD = "Tr3ndz!Shopper42"
OTHER_PASSWORD = "Fr3sh!Passw0rd77"


def make_user(email: str = "shopper@example.com", **extra: Any) -> User:
    """Create an active user with sensible defaults."""
    extra.setdefault("first_name", "Aditi")
    extra.setdefault("last_name", "Sharma")
    return User.objects.create_user(email=email, password=STRONG_PASSWORD, **extra)


class ThrottleFreeMixin:
    """Clear the throttle cache between tests.

    DRF stores throttle history in the cache, which outlives an individual
    test. Without this, the tenth registration in the suite would 429 for
    reasons unrelated to the behaviour under test.
    """

    def setUp(self) -> None:
        super().setUp()
        cache.clear()


class UserManagerTests(TestCase):
    """Invariants enforced by UserManager."""

    def test_create_user_hashes_password(self) -> None:
        user = make_user()
        self.assertNotEqual(user.password, STRONG_PASSWORD)
        self.assertTrue(user.check_password(STRONG_PASSWORD))

    def test_email_is_normalised_to_lowercase(self) -> None:
        user = make_user(email="Shopper@Example.COM")
        self.assertEqual(user.email, "shopper@example.com")

    def test_email_is_required(self) -> None:
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password=STRONG_PASSWORD, first_name="X")

    def test_create_superuser_sets_privilege_flags(self) -> None:
        admin = User.objects.create_superuser(
            email="admin@example.com", password=STRONG_PASSWORD, first_name="Admin"
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_email_verified)

    def test_superuser_cannot_drop_staff_flag(self) -> None:
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="admin@example.com",
                password=STRONG_PASSWORD,
                first_name="Admin",
                is_staff=False,
            )

    def test_duplicate_email_is_rejected_case_insensitively(self) -> None:
        make_user(email="dup@example.com")
        with self.assertRaises(DjangoValidationError):
            make_user(email="DUP@example.com")

    def test_str_returns_email(self) -> None:
        self.assertEqual(str(make_user()), "shopper@example.com")

    def test_get_full_name_collapses_empty_last_name(self) -> None:
        user = make_user(last_name="")
        self.assertEqual(user.get_full_name(), "Aditi")


class RegisterAPITests(ThrottleFreeMixin, APITestCase):
    """POST /api/v1/auth/register/"""

    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("users:register")
        self.payload = {
            "email": "new@example.com",
            "first_name": "Rohan",
            "last_name": "Mehta",
            "password": STRONG_PASSWORD,
            "confirm_password": STRONG_PASSWORD,
        }

    def test_registration_succeeds(self) -> None:
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["email"], "new@example.com")
        self.assertTrue(User.objects.filter(email="new@example.com").exists())

    def test_password_is_never_echoed_back(self) -> None:
        response = self.client.post(self.url, self.payload)
        self.assertNotIn("password", response.data)
        self.assertNotIn("confirm_password", response.data)

    def test_mismatched_passwords_rejected(self) -> None:
        response = self.client.post(
            self.url, {**self.payload, "confirm_password": "Different!123"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # Module 3 moved field errors under "errors" in the standard envelope.
        self.assertIn("confirm_password", response.data["errors"])

    def test_weak_password_rejected_by_django_validators(self) -> None:
        response = self.client.post(
            self.url, {**self.payload, "password": "12345678", "confirm_password": "12345678"}
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_email_rejected(self) -> None:
        make_user(email="new@example.com")
        response = self.client.post(self.url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"])

    def test_invalid_mobile_number_rejected(self) -> None:
        response = self.client.post(self.url, {**self.payload, "mobile_number": "abc123"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mobile_number", response.data["errors"])

    def test_response_uses_the_standard_envelope(self) -> None:
        body = self.client.post(self.url, self.payload).json()
        self.assertTrue(body["success"])
        self.assertIn("message", body)
        self.assertEqual(body["data"]["email"], "new@example.com")


class LoginAPITests(ThrottleFreeMixin, APITestCase):
    """POST /api/v1/auth/login/"""

    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("users:login")
        self.user = make_user()

    def test_login_returns_token_pair_and_user(self) -> None:
        response = self.client.post(
            self.url, {"email": self.user.email, "password": STRONG_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.user.email)

    def test_login_is_case_insensitive_on_email(self) -> None:
        response = self.client.post(
            self.url, {"email": "SHOPPER@example.com", "password": STRONG_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_wrong_password_rejected(self) -> None:
        response = self.client.post(
            self.url, {"email": self.user.email, "password": "wrong-password"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_user_cannot_log_in(self) -> None:
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            self.url, {"email": self.user.email, "password": STRONG_PASSWORD}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_is_rate_limited(self) -> None:
        for _attempt in range(10):
            self.client.post(self.url, {"email": self.user.email, "password": "nope"})
        response = self.client.post(self.url, {"email": self.user.email, "password": "nope"})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class TokenLifecycleTests(ThrottleFreeMixin, APITestCase):
    """Refresh rotation and logout blacklisting."""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user()
        response = self.client.post(
            reverse("users:login"), {"email": self.user.email, "password": STRONG_PASSWORD}
        )
        self.access = response.data["access"]
        self.refresh = response.data["refresh"]

    def test_refresh_returns_a_new_access_token(self) -> None:
        response = self.client.post(
            reverse("users:token-refresh"), {"refresh": self.refresh}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_rotated_refresh_token_cannot_be_reused(self) -> None:
        self.client.post(reverse("users:token-refresh"), {"refresh": self.refresh})
        replayed = self.client.post(
            reverse("users:token-refresh"), {"refresh": self.refresh}
        )
        self.assertEqual(replayed.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_the_refresh_token(self) -> None:
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        response = self.client.post(reverse("users:logout"), {"refresh": self.refresh})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.client.credentials()
        replayed = self.client.post(
            reverse("users:token-refresh"), {"refresh": self.refresh}
        )
        self.assertEqual(replayed.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_authentication(self) -> None:
        response = self.client.post(reverse("users:logout"), {"refresh": self.refresh})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_rejects_a_garbage_token(self) -> None:
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        response = self.client.post(reverse("users:logout"), {"refresh": "not-a-token"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ProfileAPITests(ThrottleFreeMixin, APITestCase):
    """GET/PATCH /api/v1/profile/"""

    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("users:profile")
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_anonymous_access_is_rejected(self) -> None:
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_profile_returns_the_requesting_user(self) -> None:
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["full_name"], "Aditi Sharma")

    def test_patch_updates_editable_fields(self) -> None:
        response = self.client.patch(self.url, {"first_name": "Ananya"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Ananya")

    def test_email_is_read_only(self) -> None:
        self.client.patch(self.url, {"email": "hijack@example.com"})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "shopper@example.com")

    def test_verification_flags_are_read_only(self) -> None:
        self.client.patch(self.url, {"is_email_verified": True})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_email_verified)


class ChangePasswordAPITests(ThrottleFreeMixin, APITestCase):
    """POST /api/v1/auth/change-password/"""

    def setUp(self) -> None:
        super().setUp()
        self.url = reverse("users:change-password")
        self.user = make_user()
        self.client.force_authenticate(user=self.user)

    def test_change_succeeds_and_new_password_works(self) -> None:
        response = self.client.post(
            self.url,
            {
                "current_password": STRONG_PASSWORD,
                "new_password": OTHER_PASSWORD,
                "confirm_password": OTHER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OTHER_PASSWORD))

    def test_wrong_current_password_rejected(self) -> None:
        response = self.client.post(
            self.url,
            {
                "current_password": "not-it",
                "new_password": OTHER_PASSWORD,
                "confirm_password": OTHER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("current_password", response.data["errors"])

    def test_reusing_the_current_password_rejected(self) -> None:
        response = self.client.post(
            self.url,
            {
                "current_password": STRONG_PASSWORD,
                "new_password": STRONG_PASSWORD,
                "confirm_password": STRONG_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PasswordResetFlowTests(ThrottleFreeMixin, APITestCase):
    """Forgot-password and reset-password endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.forgot_url = reverse("users:forgot-password")
        self.reset_url = reverse("users:reset-password")
        self.user = make_user()

    def test_forgot_password_sends_an_email(self) -> None:
        # Registration now also sends a welcome email, so this counts reset
        # mail specifically rather than the whole outbox.
        mail.outbox.clear()

        response = self.client.post(self.forgot_url, {"email": self.user.email})
        reset_mail = [
            message for message in mail.outbox if "Reset your" in message.subject
        ]

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(reset_mail), 1)
        self.assertIn(self.user.email, reset_mail[0].to)

    def test_unknown_email_gets_an_identical_response_and_no_email(self) -> None:
        known = self.client.post(self.forgot_url, {"email": self.user.email})
        mail.outbox.clear()
        unknown = self.client.post(self.forgot_url, {"email": "ghost@example.com"})

        self.assertEqual(unknown.status_code, known.status_code)
        self.assertEqual(unknown.data, known.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_reset_sets_the_new_password(self) -> None:
        uid, token = build_password_reset_payload(self.user)
        response = self.client.post(
            self.reset_url,
            {
                "uid": uid,
                "token": token,
                "new_password": OTHER_PASSWORD,
                "confirm_password": OTHER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OTHER_PASSWORD))

    def test_reset_token_is_single_use(self) -> None:
        uid, token = build_password_reset_payload(self.user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": OTHER_PASSWORD,
            "confirm_password": OTHER_PASSWORD,
        }
        self.client.post(self.reset_url, payload)
        replayed = self.client.post(self.reset_url, payload)
        self.assertEqual(replayed.status_code, status.HTTP_400_BAD_REQUEST)

    def test_tampered_token_rejected(self) -> None:
        uid, _token = build_password_reset_payload(self.user)
        response = self.client.post(
            self.reset_url,
            {
                "uid": uid,
                "token": "forged-token",
                "new_password": OTHER_PASSWORD,
                "confirm_password": OTHER_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_reset_is_rate_limited(self) -> None:
        for _attempt in range(5):
            self.client.post(self.forgot_url, {"email": self.user.email})
        response = self.client.post(self.forgot_url, {"email": self.user.email})
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class AddressModelTests(TestCase):
    """The single-default invariant, at the model layer."""

    def setUp(self) -> None:
        self.user = make_user()

    def make_address(self, **extra: Any) -> Address:
        defaults = {
            "user": self.user,
            "full_name": "Aditi Sharma",
            "mobile": "+919876543210",
            "address_line_1": "12 Linking Road",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "postal_code": "400050",
        }
        return Address.objects.create(**{**defaults, **extra})

    def test_first_address_becomes_default_automatically(self) -> None:
        self.assertTrue(self.make_address().is_default)

    def test_second_address_is_not_default_by_default(self) -> None:
        self.make_address()
        self.assertFalse(self.make_address(city="Pune").is_default)

    def test_promoting_an_address_demotes_the_previous_default(self) -> None:
        first = self.make_address()
        second = self.make_address(city="Pune")

        second.is_default = True
        second.save()

        first.refresh_from_db()
        self.assertFalse(first.is_default)
        self.assertTrue(Address.objects.get(pk=second.pk).is_default)

    def test_only_one_default_can_exist_per_user(self) -> None:
        self.make_address()
        self.make_address(city="Pune")
        self.assertEqual(
            Address.objects.filter(user=self.user, is_default=True).count(), 1
        )

    def test_database_constraint_blocks_a_second_default(self) -> None:
        self.make_address()
        second = self.make_address(city="Pune")
        # Bypass save() to prove the guarantee is in the database, not just
        # in application code.
        with self.assertRaises(IntegrityError):
            Address.objects.filter(pk=second.pk).update(is_default=True)

    def test_deleting_the_default_promotes_another_address(self) -> None:
        first = self.make_address()
        second = self.make_address(city="Pune")

        first.delete()
        second.refresh_from_db()
        self.assertTrue(second.is_default)

    def test_defaults_of_different_users_do_not_collide(self) -> None:
        other = make_user(email="other@example.com")
        self.make_address()
        self.make_address(user=other)
        self.assertEqual(Address.objects.filter(is_default=True).count(), 2)


class AddressAPITests(ThrottleFreeMixin, APITestCase):
    """CRUD over /api/v1/addresses/"""

    def setUp(self) -> None:
        super().setUp()
        self.user = make_user()
        self.other = make_user(email="other@example.com")
        self.client.force_authenticate(user=self.user)
        self.list_url = reverse("users:address-list")
        self.payload = {
            "full_name": "Aditi Sharma",
            "mobile": "+919876543210",
            "address_line_1": "12 Linking Road",
            "address_line_2": "Bandra West",
            "city": "Mumbai",
            "state": "Maharashtra",
            "country": "India",
            "postal_code": "400050",
        }

    def test_requires_authentication(self) -> None:
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED
        )

    def test_create_attaches_the_address_to_the_requesting_user(self) -> None:
        response = self.client.post(self.list_url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Address.objects.get(pk=response.data["id"]).user, self.user)

    def test_user_field_in_the_body_is_ignored(self) -> None:
        response = self.client.post(
            self.list_url, {**self.payload, "user": self.other.pk}
        )
        self.assertEqual(Address.objects.get(pk=response.data["id"]).user, self.user)

    def test_list_only_returns_own_addresses(self) -> None:
        self.client.post(self.list_url, self.payload)
        Address.objects.create(user=self.other, **self.payload)

        response = self.client.get(self.list_url)
        # Module 3 replaced DRF's flat {count, next, previous, results} with a
        # "pagination" block; "data" is now the bare array of results.
        self.assertEqual(response.data["pagination"]["count"], 1)
        self.assertEqual(len(response.json()["data"]), 1)

    def test_cannot_read_another_users_address(self) -> None:
        foreign = Address.objects.create(user=self.other, **self.payload)
        url = reverse("users:address-detail", args=[foreign.pk])
        self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND)

    def test_cannot_delete_another_users_address(self) -> None:
        foreign = Address.objects.create(user=self.other, **self.payload)
        url = reverse("users:address-detail", args=[foreign.pk])
        self.assertEqual(self.client.delete(url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Address.objects.filter(pk=foreign.pk).exists())

    def test_patching_is_default_switches_the_default(self) -> None:
        first = self.client.post(self.list_url, self.payload).data
        second = self.client.post(self.list_url, {**self.payload, "city": "Pune"}).data

        url = reverse("users:address-detail", args=[second["id"]])
        response = self.client.patch(url, {"is_default": True})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Address.objects.get(pk=first["id"]).is_default)
        self.assertTrue(Address.objects.get(pk=second["id"]).is_default)

    def test_invalid_mobile_is_rejected(self) -> None:
        response = self.client.post(self.list_url, {**self.payload, "mobile": "12"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("mobile", response.data["errors"])


class ValidatorTests(TestCase):
    """Unit coverage for the shared field validators."""

    def test_future_date_of_birth_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_date_of_birth(timezone.localdate() + datetime.timedelta(days=1))

    def test_under_age_date_of_birth_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_date_of_birth(timezone.localdate() - datetime.timedelta(days=365 * 5))

    def test_adult_date_of_birth_accepted(self) -> None:
        validate_date_of_birth(datetime.date(1995, 6, 15))

    def test_implausible_age_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_date_of_birth(datetime.date(1850, 1, 1))
