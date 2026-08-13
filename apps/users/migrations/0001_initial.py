"""Initial schema for the users module: User and Address."""

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import apps.users.managers
import apps.users.models
import apps.users.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="User",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("password", models.CharField(max_length=128, verbose_name="password")),
                (
                    "last_login",
                    models.DateTimeField(blank=True, null=True, verbose_name="last login"),
                ),
                (
                    "is_superuser",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates that this user has all permissions without "
                            "explicitly assigning them."
                        ),
                        verbose_name="superuser status",
                    ),
                ),
                ("first_name", models.CharField(max_length=150, verbose_name="first name")),
                (
                    "last_name",
                    models.CharField(blank=True, max_length=150, verbose_name="last name"),
                ),
                (
                    "email",
                    models.EmailField(
                        max_length=254, unique=True, verbose_name="email address"
                    ),
                ),
                (
                    "mobile_number",
                    models.CharField(
                        blank=True,
                        max_length=16,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_mobile_number",
                                message=(
                                    "Enter a valid mobile number in international "
                                    "format, for example +919876543210."
                                ),
                                regex="^\\+?[1-9]\\d{7,14}$",
                            )
                        ],
                        verbose_name="mobile number",
                    ),
                ),
                (
                    "profile_image",
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to=apps.users.models.profile_image_upload_to,
                        validators=[apps.users.validators.validate_profile_image],
                        verbose_name="profile image",
                    ),
                ),
                (
                    "date_of_birth",
                    models.DateField(
                        blank=True,
                        null=True,
                        validators=[apps.users.validators.validate_date_of_birth],
                        verbose_name="date of birth",
                    ),
                ),
                (
                    "gender",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("male", "Male"),
                            ("female", "Female"),
                            ("other", "Other"),
                            ("undisclosed", "Prefer not to say"),
                        ],
                        max_length=12,
                        verbose_name="gender",
                    ),
                ),
                (
                    "is_email_verified",
                    models.BooleanField(default=False, verbose_name="email verified"),
                ),
                (
                    "is_mobile_verified",
                    models.BooleanField(default=False, verbose_name="mobile verified"),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Unselect this instead of deleting accounts.",
                        verbose_name="active",
                    ),
                ),
                (
                    "is_staff",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "Designates whether the user can log into the admin site."
                        ),
                        verbose_name="staff status",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
                (
                    "groups",
                    models.ManyToManyField(
                        blank=True,
                        help_text=(
                            "The groups this user belongs to. A user will get all "
                            "permissions granted to each of their groups."
                        ),
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.group",
                        verbose_name="groups",
                    ),
                ),
                (
                    "user_permissions",
                    models.ManyToManyField(
                        blank=True,
                        help_text="Specific permissions for this user.",
                        related_name="user_set",
                        related_query_name="user",
                        to="auth.permission",
                        verbose_name="user permissions",
                    ),
                ),
            ],
            options={
                "verbose_name": "user",
                "verbose_name_plural": "users",
                "ordering": ["-created_at"],
            },
            managers=[
                ("objects", apps.users.managers.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name="Address",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("full_name", models.CharField(max_length=150, verbose_name="full name")),
                (
                    "mobile",
                    models.CharField(
                        max_length=16,
                        validators=[
                            django.core.validators.RegexValidator(
                                code="invalid_mobile_number",
                                message=(
                                    "Enter a valid mobile number in international "
                                    "format, for example +919876543210."
                                ),
                                regex="^\\+?[1-9]\\d{7,14}$",
                            )
                        ],
                        verbose_name="mobile",
                    ),
                ),
                (
                    "address_line_1",
                    models.CharField(max_length=255, verbose_name="address line 1"),
                ),
                (
                    "address_line_2",
                    models.CharField(
                        blank=True, max_length=255, verbose_name="address line 2"
                    ),
                ),
                ("city", models.CharField(max_length=100, verbose_name="city")),
                ("state", models.CharField(max_length=100, verbose_name="state")),
                ("country", models.CharField(max_length=100, verbose_name="country")),
                (
                    "postal_code",
                    models.CharField(max_length=16, verbose_name="postal code"),
                ),
                (
                    "is_default",
                    models.BooleanField(default=False, verbose_name="default address"),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="created at"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="updated at"),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="addresses",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "verbose_name": "address",
                "verbose_name_plural": "addresses",
                "ordering": ["-is_default", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["-created_at"], name="user_created_at_idx"),
        ),
        migrations.AddIndex(
            model_name="address",
            index=models.Index(
                fields=["user", "is_default"], name="address_user_default_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="address",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)),
                fields=("user",),
                name="unique_default_address_per_user",
            ),
        ),
    ]
