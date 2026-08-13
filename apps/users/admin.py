"""Django admin registration for users and addresses."""

from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm
from django.http import HttpRequest
from django.utils.translation import gettext_lazy as _

from apps.users.models import Address, User


class UserCreationForm(BaseUserCreationForm):
    """Admin "add user" form keyed on email.

    Django's stock form declares ``fields = ("username",)``; this model has no
    username, so the field list has to be restated.
    """

    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


class UserAdminChangeForm(UserChangeForm):
    """Admin "change user" form bound to the custom model."""

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"


class AddressInline(admin.TabularInline):
    """Edit a user's addresses from the user page."""

    model = Address
    extra = 0
    fields = (
        "full_name",
        "mobile",
        "address_line_1",
        "city",
        "state",
        "country",
        "postal_code",
        "is_default",
    )
    show_change_link = True


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin for the email-authenticated user model."""

    add_form = UserCreationForm
    form = UserAdminChangeForm
    model = User

    list_display = (
        "email",
        "get_full_name",
        "mobile_number",
        "is_email_verified",
        "is_active",
        "is_staff",
        "created_at",
    )
    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "is_email_verified",
        "is_mobile_verified",
        "gender",
    )
    search_fields = ("email", "first_name", "last_name", "mobile_number")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "last_login")
    inlines = [AddressInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal information"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "mobile_number",
                    "profile_image",
                    "date_of_birth",
                    "gender",
                )
            },
        ),
        (
            _("Verification"),
            {"fields": ("is_email_verified", "is_mobile_verified")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    @admin.display(description=_("Name"), ordering="first_name")
    def get_full_name(self, obj: User) -> str:
        """Column showing the joined name."""
        return obj.get_full_name()


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    """Admin for saved delivery addresses."""

    list_display = (
        "full_name",
        "user",
        "city",
        "state",
        "country",
        "postal_code",
        "is_default",
    )
    list_filter = ("is_default", "country", "state")
    search_fields = (
        "full_name",
        "mobile",
        "city",
        "state",
        "postal_code",
        "user__email",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    def get_queryset(self, request: HttpRequest) -> Any:
        """Join the user row so the list view does not issue N+1 queries."""
        return super().get_queryset(request).select_related("user")
