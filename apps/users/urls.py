"""URL routes for the users module, mounted by the project at /api/v1/."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.users.views import (
    AddressViewSet,
    ChangePasswordAPIView,
    ForgotPasswordAPIView,
    LoginAPIView,
    LogoutAPIView,
    ProfileAPIView,
    RegisterAPIView,
    ResetPasswordAPIView,
)

app_name = "users"

router = DefaultRouter()
router.register("addresses", AddressViewSet, basename="address")

auth_patterns: list[URLPattern | URLResolver] = [
    path("register/", RegisterAPIView.as_view(), name="register"),
    path("login/", LoginAPIView.as_view(), name="login"),
    path("logout/", LogoutAPIView.as_view(), name="logout"),
    # SimpleJWT's stock views already implement rotation and verification
    # exactly as needed; subclassing them would add code without behaviour.
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("token/verify/", TokenVerifyView.as_view(), name="token-verify"),
    path("forgot-password/", ForgotPasswordAPIView.as_view(), name="forgot-password"),
    path("reset-password/", ResetPasswordAPIView.as_view(), name="reset-password"),
    path("change-password/", ChangePasswordAPIView.as_view(), name="change-password"),
]

urlpatterns: list[URLPattern | URLResolver] = [
    path("auth/", include(auth_patterns)),
    path("profile/", ProfileAPIView.as_view(), name="profile"),
    path("", include(router.urls)),
]
