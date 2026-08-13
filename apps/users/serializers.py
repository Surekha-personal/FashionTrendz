"""Serializers for registration, authentication, profile and addresses."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Address, User

UserModel = get_user_model()


def run_password_validators(password: str, user: User | None = None) -> None:
    """Apply ``AUTH_PASSWORD_VALIDATORS`` and re-raise as a DRF error.

    Django's validators raise ``django.core.exceptions.ValidationError``, which
    DRF does not translate into a 400 response body. Converting here keeps the
    configured password policy as the single source of truth.
    """
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages)) from exc


class UserSerializer(serializers.ModelSerializer):
    """Read and update representation of the authenticated user's profile."""

    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "mobile_number",
            "profile_image",
            "date_of_birth",
            "gender",
            "is_email_verified",
            "is_mobile_verified",
            "created_at",
            "updated_at",
        )
        # Email is immutable over this endpoint: changing a login identifier
        # requires a verification round-trip, which is its own flow.
        # The verification flags are set by the server, never by the client.
        read_only_fields = (
            "id",
            "email",
            "is_email_verified",
            "is_mobile_verified",
            "created_at",
            "updated_at",
        )

    def get_full_name(self, obj: User) -> str:
        """Expose the joined name so the frontend does not re-implement it."""
        return obj.get_full_name()


class RegisterSerializer(serializers.ModelSerializer):
    """Create a new storefront account."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        trim_whitespace=False,
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = (
            "email",
            "first_name",
            "last_name",
            "mobile_number",
            "date_of_birth",
            "gender",
            "password",
            "confirm_password",
        )

    def validate_email(self, value: str) -> str:
        """Reject an email already in use, comparing case-insensitively."""
        normalised = UserModel.objects.normalize_email(value).lower()
        if UserModel.objects.filter(email=normalised).exists():
            raise serializers.ValidationError(
                _("An account with this email address already exists.")
            )
        return normalised

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Confirm the two password fields agree and meet the password policy."""
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("The two password fields do not match.")}
            )

        # Build an unsaved instance so UserAttributeSimilarityValidator can
        # compare the password against this user's own name and email.
        candidate = User(
            email=attrs["email"],
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )
        run_password_validators(attrs["password"], candidate)
        return attrs

    def create(self, validated_data: dict[str, Any]) -> User:
        """Create the account through the manager so hashing is guaranteed."""
        validated_data.pop("confirm_password")
        password = validated_data.pop("password")
        return UserModel.objects.create_user(password=password, **validated_data)


class LoginSerializer(TokenObtainPairSerializer):
    """Exchange email and password for an access/refresh token pair."""

    @classmethod
    def get_token(cls, user: User) -> RefreshToken:
        """Embed display claims so the frontend can render without an extra call."""
        token = super().get_token(user)
        token["email"] = user.email
        token["full_name"] = user.get_full_name()
        token["is_staff"] = user.is_staff
        return token

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Return the token pair alongside the serialised user."""
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class LogoutSerializer(serializers.Serializer):
    """Blacklist a refresh token, ending the session server-side."""

    refresh = serializers.CharField(write_only=True)

    def validate_refresh(self, value: str) -> str:
        """Reject a malformed or already-expired refresh token."""
        try:
            self.token = RefreshToken(value)
        except Exception as exc:  # TokenError and its subclasses
            raise serializers.ValidationError(
                _("This refresh token is invalid or has already expired.")
            ) from exc
        return value

    def save(self, **kwargs: Any) -> None:
        """Add the token's jti to the blacklist so it cannot be reused."""
        self.token.blacklist()


class ChangePasswordSerializer(serializers.Serializer):
    """Change the password of an already-authenticated user."""

    current_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    def validate_current_password(self, value: str) -> str:
        """Require the existing password before allowing a change."""
        user: User = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Your current password is incorrect."))
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Check the confirmation matches and the new password is acceptable."""
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("The two password fields do not match.")}
            )

        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": _("The new password must differ from the current one.")}
            )

        run_password_validators(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs: Any) -> User:
        """Persist the new password hash."""
        user: User = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    """Accept an email address and start the password reset flow."""

    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        """Normalise only. Existence is deliberately not checked.

        Reporting "no such account" here would turn this endpoint into an
        account-enumeration oracle. The view answers identically either way.
        """
        return UserModel.objects.normalize_email(value).lower()

    def get_user(self) -> User | None:
        """Return the matching active user, or None if there is not one."""
        return UserModel.objects.filter(
            email=self.validated_data["email"], is_active=True
        ).first()


class ResetPasswordSerializer(serializers.Serializer):
    """Complete a password reset using the emailed uid/token pair."""

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )
    confirm_password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, trim_whitespace=False
    )

    default_error_messages = {
        "invalid_link": _("This password reset link is invalid or has expired."),
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Resolve the uid, verify the token, then validate the new password."""
        try:
            user_pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = UserModel.objects.get(pk=user_pk, is_active=True)
        except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
            self.fail("invalid_link")

        # The token hash includes the current password hash and last_login, so
        # it self-invalidates once used or once the password changes elsewhere.
        if not default_token_generator.check_token(user, attrs["token"]):
            self.fail("invalid_link")

        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": _("The two password fields do not match.")}
            )

        run_password_validators(attrs["new_password"], user)
        attrs["user"] = user
        return attrs

    def save(self, **kwargs: Any) -> User:
        """Set the new password hash, invalidating the reset link."""
        user: User = self.validated_data["user"]
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


class AddressSerializer(serializers.ModelSerializer):
    """Full representation of a saved delivery address."""

    class Meta:
        model = Address
        fields = (
            "id",
            "full_name",
            "mobile",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "postal_code",
            "is_default",
            "created_at",
            "updated_at",
        )
        # The owner is taken from the authenticated request, never the body,
        # so a client cannot write an address into someone else's account.
        read_only_fields = ("id", "created_at", "updated_at")

    def create(self, validated_data: dict[str, Any]) -> Address:
        """Attach the address to the requesting user."""
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


def build_password_reset_payload(user: User) -> tuple[str, str]:
    """Return the ``(uid, token)`` pair used to build a reset link."""
    return urlsafe_base64_encode(force_bytes(user.pk)), default_token_generator.make_token(user)
