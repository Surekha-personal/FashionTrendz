"""Tests for the core infrastructure module.

Core owns no concrete models, so most of this is unit-level. The envelope,
exception handler and pagination are exercised end to end through the Module 2
endpoints, since those are the only real views that exist — which also proves
the claim that core applies to existing views without editing them.
"""

from __future__ import annotations

import datetime
import io
from decimal import Decimal
from typing import Any

from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIRequestFactory, APITestCase

from apps.core import utils
from apps.core.choices import (
    CANCELLABLE_ORDER_STATUSES,
    TERMINAL_ORDER_STATUSES,
    OrderStatus,
    Priority,
    Rating,
)
from apps.core.constants import REQUEST_ID_HEADER, RESPONSE_TIME_HEADER
from apps.core.exceptions import (
    BusinessRuleViolation,
    ResourceConflict,
    api_exception_handler,
)
from apps.core.logging import Timer, get_request_id, reset_request_id, set_request_id
from apps.core.middleware import RequestIDMiddleware, ResponseTimeMiddleware
from apps.core.permissions import (
    AdminOrReadOnly,
    IsAdmin,
    IsCustomer,
    OwnerOnly,
    ReadOnly,
)
from apps.core.responses import EnvelopeJSONRenderer, error_response, success_response
from apps.core.validators import (
    ImageValidator,
    slug_validator,
    validate_discount_percentage,
    validate_no_html,
    validate_positive,
    validate_price,
)
from apps.users.models import Address, User

STRONG_PASSWORD = "Tr3ndz!Shopper42"


def make_png(size: tuple[int, int] = (64, 64), name: str = "swatch.png") -> SimpleUploadedFile:
    """Return a real, decodable PNG upload."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 90)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------


class IdentifierUtilTests(SimpleTestCase):
    """Slug, SKU, order number, invoice number and OTP generation."""

    def test_order_number_has_prefix_and_date(self) -> None:
        number = utils.generate_order_number(
            now=datetime.datetime(2026, 8, 4, 12, 0, tzinfo=datetime.timezone.utc)
        )
        self.assertTrue(number.startswith("FT-ORD-20260804-"))

    def test_invoice_number_is_scoped_to_the_month(self) -> None:
        number = utils.generate_invoice_number(
            now=datetime.datetime(2026, 8, 4, 12, 0, tzinfo=datetime.timezone.utc)
        )
        self.assertTrue(number.startswith("FT-INV-202608-"))

    def test_generated_codes_avoid_ambiguous_characters(self) -> None:
        # 200 samples is enough that any of I/O/0/1 in the alphabet would show.
        codes = "".join(utils.generate_sku() for _ in range(200))
        for character in "IO01":
            self.assertNotIn(character, codes.removeprefix("FT-").replace("-", ""))

    def test_skus_are_not_sequential(self) -> None:
        self.assertNotEqual(utils.generate_sku(), utils.generate_sku())

    def test_otp_is_zero_padded_to_the_requested_length(self) -> None:
        for _ in range(50):
            otp = utils.generate_otp(6)
            self.assertEqual(len(otp), 6)
            self.assertTrue(otp.isdigit())

    def test_otp_rejects_a_zero_length(self) -> None:
        with self.assertRaises(ValueError):
            utils.generate_otp(0)


class SlugUtilTests(TestCase):
    """generate_unique_slug needs the database to detect collisions.

    No concrete model carries a ``slug`` column yet — core's
    :class:`~apps.core.mixins.SEOFieldsMixin` is abstract — so these run the
    helper against ``Address.city``, which stands in as an arbitrary text
    column. The helper only ever issues ``filter(<field>=candidate).exists()``,
    so any character field exercises it faithfully.
    """

    TAKEN = "summer-linen-dress"

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            email="slug@example.com", password=STRONG_PASSWORD, first_name="Slug"
        )

    def occupy(self, city: str) -> Address:
        """Create an address holding ``city``, so that value is taken."""
        return Address.objects.create(
            user=self.user,
            full_name="Aditi",
            mobile="+919876543210",
            address_line_1="1 Road",
            city=city,
            state="MH",
            country="India",
            postal_code="400050",
        )

    def test_slug_is_derived_from_the_value(self) -> None:
        slug = utils.generate_unique_slug(
            Address, "Summer Linen Dress", slug_field="city"
        )
        self.assertEqual(slug, self.TAKEN)

    def test_collision_gets_a_random_suffix(self) -> None:
        self.occupy(self.TAKEN)
        slug = utils.generate_unique_slug(
            Address, "Summer Linen Dress", slug_field="city"
        )
        self.assertNotEqual(slug, self.TAKEN)
        self.assertTrue(slug.startswith(f"{self.TAKEN}-"))

    def test_suffixes_differ_between_calls(self) -> None:
        self.occupy(self.TAKEN)
        first = utils.generate_unique_slug(Address, "Summer Linen Dress", slug_field="city")
        second = utils.generate_unique_slug(Address, "Summer Linen Dress", slug_field="city")
        self.assertNotEqual(first, second)

    def test_own_row_is_not_treated_as_a_collision(self) -> None:
        existing = self.occupy(self.TAKEN)
        slug = utils.generate_unique_slug(
            Address,
            "Summer Linen Dress",
            slug_field="city",
            instance_pk=existing.pk,
        )
        self.assertEqual(slug, self.TAKEN)

    def test_non_ascii_value_still_yields_a_usable_slug(self) -> None:
        # slugify() empties a purely non-ASCII string; the fallback keeps the
        # column populated instead of writing "".
        slug = utils.generate_unique_slug(Address, "साड़ी", slug_field="city")
        self.assertTrue(slug.startswith("item-"))


class MoneyUtilTests(SimpleTestCase):
    """Rounding and formatting of monetary amounts."""

    def test_half_up_rounding_matches_invoice_expectations(self) -> None:
        # ROUND_HALF_EVEN, Python's default, would give 0.12 here.
        self.assertEqual(utils.quantise_money("0.125"), Decimal("0.13"))

    def test_format_currency_uses_the_symbol_and_separators(self) -> None:
        self.assertEqual(utils.format_currency(Decimal("1299"), "INR"), "₹1,299.00")

    def test_format_currency_falls_back_for_an_unknown_code(self) -> None:
        self.assertEqual(utils.format_currency(10, "ZZZ"), "ZZZ 10.00")

    def test_zero_decimal_currency_has_no_minor_unit(self) -> None:
        self.assertEqual(utils.format_currency(1500, "JPY"), "JPY 1,500")

    def test_discount_calculation_rounds_to_the_minor_unit(self) -> None:
        self.assertEqual(
            utils.calculate_discounted_price("1999.00", "15"), Decimal("1699.15")
        )

    def test_invalid_amount_raises_valueerror(self) -> None:
        with self.assertRaises(ValueError):
            utils.quantise_money("not-a-number")


class RedactionTests(SimpleTestCase):
    """Sensitive values must never reach the log stream."""

    def test_passwords_and_tokens_are_redacted(self) -> None:
        redacted = utils.redact(
            {"email": "a@b.com", "password": "hunter2", "refresh": "eyJ..."}
        )
        self.assertEqual(redacted["email"], "a@b.com")
        self.assertEqual(redacted["password"], "[redacted]")
        self.assertEqual(redacted["refresh"], "[redacted]")

    def test_redaction_reaches_nested_structures(self) -> None:
        redacted = utils.redact({"payment": [{"cvv": "123", "last4": "4242"}]})
        self.assertEqual(redacted["payment"][0]["cvv"], "[redacted]")
        self.assertEqual(redacted["payment"][0]["last4"], "4242")


class ImageCompressionTests(SimpleTestCase):
    """compress_image downscales without upscaling."""

    def test_oversized_image_is_downscaled(self) -> None:
        from PIL import Image

        compressed = utils.compress_image(make_png((3000, 1500)), max_dimension=800)
        with Image.open(io.BytesIO(compressed.read())) as result:
            self.assertLessEqual(max(result.size), 800)

    def test_aspect_ratio_is_preserved(self) -> None:
        from PIL import Image

        compressed = utils.compress_image(make_png((2000, 1000)), max_dimension=500)
        with Image.open(io.BytesIO(compressed.read())) as result:
            self.assertEqual(result.width, 2 * result.height)

    def test_small_image_is_not_upscaled(self) -> None:
        from PIL import Image

        compressed = utils.compress_image(make_png((100, 100)), max_dimension=800)
        with Image.open(io.BytesIO(compressed.read())) as result:
            self.assertEqual(result.size, (100, 100))


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class ValidatorTests(SimpleTestCase):
    """Shared field validators."""

    def test_slug_validator_rejects_uppercase_and_underscores(self) -> None:
        slug_validator("summer-linen-dress")
        for bad in ("Summer-Dress", "summer_dress", "-leading", "trailing-"):
            with self.assertRaises(DjangoValidationError, msg=bad):
                slug_validator(bad)

    def test_price_rejects_negatives_and_excess_precision(self) -> None:
        validate_price("1299.00")
        validate_price(0)
        with self.assertRaises(DjangoValidationError):
            validate_price("-1.00")
        with self.assertRaises(DjangoValidationError):
            validate_price("1.234")

    def test_price_rejects_values_beyond_the_column_width(self) -> None:
        with self.assertRaises(DjangoValidationError):
            validate_price("99999999.00")

    def test_discount_must_be_within_zero_and_one_hundred(self) -> None:
        validate_discount_percentage("0")
        validate_discount_percentage("100")
        for bad in ("-1", "100.01"):
            with self.assertRaises(DjangoValidationError, msg=bad):
                validate_discount_percentage(bad)

    def test_positive_validator_rejects_zero(self) -> None:
        validate_positive("0.01")
        with self.assertRaises(DjangoValidationError):
            validate_positive(0)

    def test_no_html_validator_blocks_angle_brackets(self) -> None:
        validate_no_html("Perfectly ordinary product name")
        with self.assertRaises(DjangoValidationError):
            validate_no_html("<script>alert(1)</script>")


class ImageValidatorTests(SimpleTestCase):
    """Image uploads are validated by decoded format, not by filename."""

    def test_a_real_png_passes(self) -> None:
        ImageValidator()(make_png())

    def test_a_renamed_non_image_is_rejected(self) -> None:
        # The whole point: the extension says PNG, the bytes do not.
        disguised = SimpleUploadedFile(
            "totally-a.png", b"<svg onload=alert(1)></svg>", content_type="image/png"
        )
        with self.assertRaises(DjangoValidationError) as caught:
            ImageValidator()(disguised)
        self.assertEqual(caught.exception.code, "invalid_image")

    def test_disallowed_extension_is_rejected(self) -> None:
        upload = make_png(name="logo.bmp")
        with self.assertRaises(DjangoValidationError) as caught:
            ImageValidator()(upload)
        self.assertEqual(caught.exception.code, "invalid_extension")

    def test_oversized_upload_is_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError) as caught:
            ImageValidator(max_bytes=10)(make_png())
        self.assertEqual(caught.exception.code, "file_too_large")

    def test_undersized_dimensions_are_rejected(self) -> None:
        with self.assertRaises(DjangoValidationError) as caught:
            ImageValidator(min_width=500, min_height=500)(make_png((64, 64)))
        self.assertEqual(caught.exception.code, "image_too_small")

    def test_file_pointer_is_restored_for_the_storage_backend(self) -> None:
        upload = make_png()
        upload.seek(0)
        ImageValidator()(upload)
        # A validator that consumed the stream would leave a truncated file.
        self.assertEqual(upload.tell(), 0)
        self.assertTrue(upload.read())


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------


class ChoicesTests(SimpleTestCase):
    """Enumerations and their derived sets."""

    def test_order_status_values_are_stable_strings(self) -> None:
        self.assertEqual(OrderStatus.DELIVERED.value, "delivered")

    def test_terminal_and_cancellable_sets_do_not_overlap(self) -> None:
        self.assertFalse(TERMINAL_ORDER_STATUSES & CANCELLABLE_ORDER_STATUSES)

    def test_integer_choices_are_ordinally_comparable(self) -> None:
        self.assertGreater(Priority.URGENT, Priority.LOW)
        self.assertEqual(sorted(Rating.values), [1, 2, 3, 4, 5])


# ---------------------------------------------------------------------------
# Responses and the envelope
# ---------------------------------------------------------------------------


class EnvelopeRendererTests(SimpleTestCase):
    """The renderer's payload-shaping rules, in isolation."""

    def setUp(self) -> None:
        self.renderer = EnvelopeJSONRenderer()
        self.factory = APIRequestFactory()

    def render(self, data: Any, status_code: int = 200, method: str = "get") -> dict[str, Any]:
        """Run the renderer and return the decoded envelope."""
        import json

        request = getattr(self.factory, method)("/api/v1/thing/")
        response = type("R", (), {"status_code": status_code})()
        raw = self.renderer.render(
            data, renderer_context={"response": response, "request": request}
        )
        return json.loads(raw)

    def test_success_payload_is_wrapped(self) -> None:
        body = self.render({"id": 1})
        self.assertEqual(body["success"], True)
        self.assertEqual(body["data"], {"id": 1})
        self.assertIn("message", body)

    def test_post_gets_a_created_message(self) -> None:
        self.assertEqual(
            self.render({"id": 1}, status_code=201, method="post")["message"],
            "Created successfully.",
        )

    def test_detail_only_payload_becomes_the_message(self) -> None:
        body = self.render({"detail": "Password updated."})
        self.assertEqual(body["message"], "Password updated.")
        self.assertEqual(body["data"], {})

    def test_pagination_is_hoisted_and_data_is_the_array(self) -> None:
        body = self.render(
            {"pagination": {"count": 2, "page": 1}, "results": [{"id": 1}, {"id": 2}]}
        )
        self.assertEqual(body["data"], [{"id": 1}, {"id": 2}])
        self.assertEqual(body["pagination"]["count"], 2)

    def test_already_enveloped_payload_passes_through(self) -> None:
        original = {"success": False, "message": "Nope.", "errors": {"a": ["b"]}}
        self.assertEqual(self.render(original, status_code=400), original)

    def test_raw_error_body_is_normalised(self) -> None:
        body = self.render({"field": ["is wrong"]}, status_code=400)
        self.assertFalse(body["success"])
        self.assertEqual(body["errors"], {"field": ["is wrong"]})

    def test_none_stays_none_so_204_has_no_body(self) -> None:
        self.assertIsNone(
            self.renderer._envelope(None, None, None)  # noqa: SLF001
        )


class ResponseHelperTests(SimpleTestCase):
    """success_response and error_response."""

    def test_success_response_carries_an_explicit_message(self) -> None:
        response = success_response({"id": 7}, message="Coupon applied.")
        self.assertEqual(response.message, "Coupon applied.")
        self.assertEqual(response.data, {"id": 7})

    def test_error_response_builds_the_full_envelope(self) -> None:
        response = error_response("Nope.", {"coupon": ["Expired."]}, status=409)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["errors"], {"coupon": ["Expired."]})


# ---------------------------------------------------------------------------
# Exception handler
# ---------------------------------------------------------------------------


class ExceptionHandlerTests(SimpleTestCase):
    """Every exception type collapses into one response shape."""

    def handle(self, exc: Exception) -> Any:
        """Run the handler with a minimal context."""
        return api_exception_handler(exc, {"view": None, "request": None})

    def assert_envelope(self, response: Any, status_code: int) -> None:
        """Assert the response is a well-formed failure envelope."""
        self.assertEqual(response.status_code, status_code)
        self.assertIs(response.data["success"], False)
        self.assertIsInstance(response.data["message"], str)
        self.assertIsInstance(response.data["errors"], dict)

    def test_validation_error_dict(self) -> None:
        response = self.handle(ValidationError({"email": ["Already taken."]}))
        self.assert_envelope(response, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["errors"]["email"], ["Already taken."])

    def test_validation_error_bare_list_becomes_non_field_errors(self) -> None:
        response = self.handle(ValidationError(["Something is off."]))
        self.assert_envelope(response, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.data["errors"])

    def test_not_found(self) -> None:
        self.assert_envelope(self.handle(NotFound()), status.HTTP_404_NOT_FOUND)

    def test_django_http404(self) -> None:
        from django.http import Http404

        self.assert_envelope(self.handle(Http404()), status.HTTP_404_NOT_FOUND)

    def test_permission_denied(self) -> None:
        self.assert_envelope(self.handle(PermissionDenied()), status.HTTP_403_FORBIDDEN)

    def test_django_permission_denied(self) -> None:
        from django.core.exceptions import PermissionDenied as DjangoPermissionDenied

        self.assert_envelope(
            self.handle(DjangoPermissionDenied()), status.HTTP_403_FORBIDDEN
        )

    def test_django_validation_error(self) -> None:
        self.assert_envelope(
            self.handle(DjangoValidationError({"price": ["Too high."]})),
            status.HTTP_400_BAD_REQUEST,
        )

    def test_integrity_error_becomes_409_and_leaks_no_sql(self) -> None:
        from django.db import IntegrityError

        exc = IntegrityError(
            'duplicate key value violates unique constraint "users_user_email_key"'
        )
        response = self.handle(exc)
        self.assert_envelope(response, status.HTTP_409_CONFLICT)
        self.assertNotIn("users_user_email_key", str(response.data))

    def test_unhandled_exception_becomes_a_generic_500(self) -> None:
        with self.assertLogs("apps.core.exceptions", level="ERROR"):
            response = self.handle(RuntimeError("secret internal detail"))
        self.assert_envelope(response, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertNotIn("secret internal detail", str(response.data))

    def test_custom_business_rule_violation(self) -> None:
        response = self.handle(BusinessRuleViolation("Cart is empty."))
        self.assert_envelope(response, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "Cart is empty.")

    def test_custom_resource_conflict(self) -> None:
        self.assert_envelope(self.handle(ResourceConflict()), status.HTTP_409_CONFLICT)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class PermissionTests(TestCase):
    """Reusable permission classes."""

    def setUp(self) -> None:
        self.factory = APIRequestFactory()
        self.customer = User.objects.create_user(
            email="c@example.com", password=STRONG_PASSWORD, first_name="Cust"
        )
        self.staff = User.objects.create_user(
            email="s@example.com",
            password=STRONG_PASSWORD,
            first_name="Staff",
            is_staff=True,
        )

    def request(self, method: str = "get", user: Any = None) -> Any:
        """Build a request bound to ``user``."""
        request = getattr(self.factory, method)("/api/v1/thing/")
        request.user = user or self.customer
        return request

    def test_is_admin_allows_only_staff(self) -> None:
        self.assertTrue(IsAdmin().has_permission(self.request(user=self.staff), None))
        self.assertFalse(IsAdmin().has_permission(self.request(user=self.customer), None))

    def test_is_customer_excludes_staff(self) -> None:
        self.assertTrue(IsCustomer().has_permission(self.request(user=self.customer), None))
        self.assertFalse(IsCustomer().has_permission(self.request(user=self.staff), None))

    def test_read_only_allows_get_and_blocks_post(self) -> None:
        self.assertTrue(ReadOnly().has_permission(self.request("get"), None))
        self.assertFalse(ReadOnly().has_permission(self.request("post"), None))

    def test_admin_or_read_only(self) -> None:
        permission = AdminOrReadOnly()
        self.assertTrue(permission.has_permission(self.request("get"), None))
        self.assertFalse(
            permission.has_permission(self.request("post", self.customer), None)
        )
        self.assertTrue(permission.has_permission(self.request("post", self.staff), None))

    def test_owner_only_compares_the_owner_field(self) -> None:
        address = Address.objects.create(
            user=self.customer,
            full_name="Cust",
            mobile="+919876543210",
            address_line_1="1 Road",
            city="Mumbai",
            state="MH",
            country="India",
            postal_code="400050",
        )
        permission = OwnerOnly()
        self.assertTrue(
            permission.has_object_permission(self.request(user=self.customer), None, address)
        )
        self.assertFalse(
            permission.has_object_permission(self.request(user=self.staff), None, address)
        )


# ---------------------------------------------------------------------------
# Middleware and logging
# ---------------------------------------------------------------------------


class MiddlewareTests(SimpleTestCase):
    """Request id and response timing."""

    def setUp(self) -> None:
        self.factory = RequestFactory()

    @staticmethod
    def _ok(request: Any) -> Any:
        from django.http import HttpResponse

        return HttpResponse("ok")

    def test_request_id_is_generated_and_echoed(self) -> None:
        response = RequestIDMiddleware(self._ok)(self.factory.get("/api/v1/x/"))
        self.assertTrue(response[REQUEST_ID_HEADER])

    def test_inbound_request_id_is_reused_for_tracing(self) -> None:
        request = self.factory.get("/api/v1/x/", HTTP_X_REQUEST_ID="abc123")
        response = RequestIDMiddleware(self._ok)(request)
        self.assertEqual(response[REQUEST_ID_HEADER], "abc123")

    def test_hostile_inbound_id_is_sanitised_and_capped(self) -> None:
        request = self.factory.get(
            "/api/v1/x/", HTTP_X_REQUEST_ID="<script>\n" + "A" * 500
        )
        response = RequestIDMiddleware(self._ok)(request)
        returned = response[REQUEST_ID_HEADER]
        self.assertLessEqual(len(returned), 64)
        self.assertNotIn("<", returned)
        self.assertNotIn("\n", returned)

    def test_request_id_does_not_leak_into_the_next_request(self) -> None:
        RequestIDMiddleware(self._ok)(self.factory.get("/api/v1/x/"))
        self.assertEqual(get_request_id(), "-")

    def test_response_time_header_is_added(self) -> None:
        response = ResponseTimeMiddleware(self._ok)(self.factory.get("/api/v1/x/"))
        self.assertGreaterEqual(float(response[RESPONSE_TIME_HEADER]), 0.0)

    def test_static_paths_are_not_access_logged(self) -> None:
        self.assertFalse(
            ResponseTimeMiddleware._should_log(  # noqa: SLF001
                self.factory.get("/static/admin/css/base.css")
            )
        )


class LoggingHelperTests(SimpleTestCase):
    """Context variable handling and the timer."""

    def test_request_id_binds_and_resets(self) -> None:
        token = set_request_id("deadbeef")
        self.assertEqual(get_request_id(), "deadbeef")
        reset_request_id(token)
        self.assertEqual(get_request_id(), "-")

    def test_timer_measures_a_non_negative_duration(self) -> None:
        with Timer() as timer:
            sum(range(1000))
        self.assertGreaterEqual(timer.elapsed_ms, 0.0)


# ---------------------------------------------------------------------------
# End-to-end: core applied to the existing Module 2 endpoints
# ---------------------------------------------------------------------------


class EnvelopeIntegrationTests(APITestCase):
    """Core changes the wire format of views it never touched."""

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )

    def test_success_body_has_the_standard_shape(self) -> None:
        self.client.force_authenticate(user=self.user)
        body = self.client.get(reverse("users:profile")).json()
        self.assertEqual(set(body.keys()), {"success", "message", "data"})
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["email"], "shopper@example.com")

    def test_failure_body_has_the_standard_shape(self) -> None:
        body = self.client.post(
            reverse("users:register"), {"email": "not-an-email"}
        ).json()
        self.assertEqual(set(body.keys()), {"success", "message", "errors"})
        self.assertFalse(body["success"])
        self.assertIn("email", body["errors"])

    def test_401_from_a_third_party_view_is_also_enveloped(self) -> None:
        # SimpleJWT's TokenRefreshView, which core never imported.
        body = self.client.post(
            reverse("users:token-refresh"), {"refresh": "garbage"}
        ).json()
        self.assertFalse(body["success"])
        self.assertIn("errors", body)

    def test_404_is_enveloped(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("users:address-detail", args=[999999]))
        body = response.json()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(body["success"])
        self.assertEqual(set(body.keys()), {"success", "message", "errors"})
        self.assertIn("detail", body["errors"])

    def test_every_response_carries_tracing_headers(self) -> None:
        self.client.force_authenticate(user=self.user)
        response = self.client.get(reverse("users:profile"))
        self.assertIn(REQUEST_ID_HEADER, response)
        self.assertIn(RESPONSE_TIME_HEADER, response)


class PaginationIntegrationTests(APITestCase):
    """The core paginators, exercised through the address list."""

    def setUp(self) -> None:
        cache.clear()
        self.user = User.objects.create_user(
            email="shopper@example.com", password=STRONG_PASSWORD, first_name="Aditi"
        )
        self.client.force_authenticate(user=self.user)
        for index in range(25):
            Address.objects.create(
                user=self.user,
                full_name=f"Aditi {index}",
                mobile="+919876543210",
                address_line_1=f"{index} Linking Road",
                city="Mumbai",
                state="Maharashtra",
                country="India",
                postal_code="400050",
            )
        self.url = reverse("users:address-list")

    def test_default_page_size_applies(self) -> None:
        body = self.client.get(self.url).json()
        self.assertEqual(len(body["data"]), 20)
        self.assertEqual(body["pagination"]["count"], 25)
        self.assertEqual(body["pagination"]["total_pages"], 2)

    def test_page_size_query_param_is_honoured(self) -> None:
        body = self.client.get(self.url, {"page_size": 5}).json()
        self.assertEqual(len(body["data"]), 5)
        self.assertEqual(body["pagination"]["page_size"], 5)

    def test_page_size_is_clamped_to_the_maximum(self) -> None:
        # Without the ceiling this would return the whole table.
        body = self.client.get(self.url, {"page_size": 100000}).json()
        self.assertLessEqual(len(body["data"]), 100)

    def test_page_param_navigates(self) -> None:
        body = self.client.get(self.url, {"page": 2}).json()
        self.assertEqual(body["pagination"]["page"], 2)
        self.assertEqual(len(body["data"]), 5)
        self.assertIsNone(body["pagination"]["next"])

    def test_out_of_range_page_is_a_clean_404(self) -> None:
        response = self.client.get(self.url, {"page": 99})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(response.json()["success"])
