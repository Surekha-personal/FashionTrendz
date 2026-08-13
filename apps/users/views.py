"""API views for registration, authentication, profile and addresses."""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import QuerySet
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status, viewsets
from rest_framework.generics import CreateAPIView, GenericAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.users.models import Address, User
from apps.users.permissions import IsOwner
from apps.users.serializers import (
    AddressSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserSerializer,
    build_password_reset_payload,
)

logger = logging.getLogger(__name__)


def send_password_reset_email(user: User, uid: str, token: str) -> None:
    """Email a password reset link pointing at the Next.js frontend.

    Delegates to the notifications module, which owns the copy, the delivery
    ledger and the retry path. The message itself lives in
    ``notifications/templates.py`` under the ``password_reset`` key.

    Kept as a named function rather than inlined at the call site so the
    existing caller and its error handling are unchanged.
    """
    from apps.notifications import services as notifications

    notifications.notify(
        user,
        "password_reset",
        {
            "reset_url": settings.PASSWORD_RESET_URL_TEMPLATE.format(
                uid=uid, token=token
            ),
            "timeout_hours": settings.PASSWORD_RESET_TIMEOUT // 3600,
        },
        # A reset request must reach the account whatever the customer has
        # switched off. It is a security notice, not a subscription.
        force=True,
    )


@extend_schema(
    tags=["Authentication"],
    summary="Register a new account",
    responses={201: UserSerializer},
)
class RegisterAPIView(CreateAPIView):
    """Create a storefront account.

    Returns the created profile without tokens: the client calls the login
    endpoint next. Keeping registration and session establishment separate
    means a future email-verification gate can block login without touching
    this view.
    """

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "register"

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Create the user and respond with the profile representation."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


@extend_schema(
    tags=["Authentication"],
    summary="Obtain an access and refresh token pair",
    examples=[
        OpenApiExample(
            "Credentials",
            value={"email": "shopper@example.com", "password": "correct horse battery"},
            request_only=True,
        )
    ],
)
class LoginAPIView(TokenObtainPairView):
    """Authenticate with email and password, returning tokens plus the user."""

    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


@extend_schema(
    tags=["Authentication"],
    summary="Blacklist a refresh token",
    responses={204: OpenApiResponse(description="Refresh token blacklisted.")},
)
class LogoutAPIView(GenericAPIView):
    """End the session by blacklisting the supplied refresh token.

    The access token stays technically valid until it expires — that is
    inherent to stateless JWTs — which is why access lifetimes are short.
    """

    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Blacklist the token and return an empty 204."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(
    tags=["Authentication"],
    summary="Request a password reset email",
    responses={
        200: OpenApiResponse(
            description="Always returned, whether or not the address is registered."
        )
    },
)
class ForgotPasswordAPIView(GenericAPIView):
    """Send a reset link to the address if it belongs to an active account."""

    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Respond identically for known and unknown addresses."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.get_user()

        if user is not None:
            uid, token = build_password_reset_payload(user)
            try:
                send_password_reset_email(user, uid, token)
            except Exception:
                # A failed send must not change the response shape, or the
                # difference becomes an account-enumeration signal.
                logger.exception("Password reset email failed for user %s", user.pk)

        return Response(
            {
                "detail": (
                    "If an account exists for that email address, "
                    "a password reset link has been sent."
                )
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Authentication"],
    summary="Set a new password using an emailed reset token",
    responses={200: OpenApiResponse(description="Password updated.")},
)
class ResetPasswordAPIView(GenericAPIView):
    """Complete the reset flow started by the forgot-password endpoint."""

    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Validate the uid/token pair and store the new password."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Your password has been reset. You can now sign in."},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Authentication"],
    summary="Change the password of the signed-in user",
    responses={200: OpenApiResponse(description="Password updated.")},
)
class ChangePasswordAPIView(GenericAPIView):
    """Change a password when the current one is known."""

    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Verify the current password, then store the new one."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
                "detail": (
                    "Password updated. Existing refresh tokens remain valid until "
                    "they expire; sign out on other devices to revoke them."
                )
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(tags=["Profile"])
class ProfileAPIView(RetrieveUpdateAPIView):
    """Read or update the signed-in user's own profile.

    ``GET`` serves the profile screen; ``PATCH`` handles partial edits and
    avatar uploads. There is no ``DELETE``: account deletion in an ecommerce
    context has order-history implications that belong in their own module.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self) -> User:
        """Always resolve to the requesting user — the URL carries no id."""
        return self.request.user


@extend_schema(tags=["Addresses"])
class AddressViewSet(viewsets.ModelViewSet):
    """Full CRUD over the signed-in user's delivery addresses.

    Marking an address default is a ``PATCH`` with ``is_default: true``; the
    model demotes the previous default inside the same transaction.
    """

    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    filterset_fields = ["city", "state", "country", "is_default"]
    search_fields = ["full_name", "city", "state", "postal_code"]
    ordering_fields = ["created_at", "updated_at", "city"]

    def get_queryset(self) -> QuerySet[Address]:
        """Scope every action to the requesting user's own addresses."""
        # drf-spectacular introspects the view with an anonymous user during
        # schema generation; return an empty set rather than raising.
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Address.objects.none()
        return Address.objects.filter(user=self.request.user)
