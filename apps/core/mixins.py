"""Abstract model and view mixins.

Every model class here sets ``abstract = True``, so **this module creates no
tables and generates no migration**. Migrations appear only in the concrete
apps that inherit from these classes — the columns land in *their* migration
files, in their own app.

One rule when combining them: a model may inherit at most one mixin that
declares a manager. Only :class:`SoftDeleteMixin` does, so any other
combination is safe.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.choices import PublishStatus
from apps.core.constants import SLUG_MAX_LENGTH

# ---------------------------------------------------------------------------
# Model mixins
# ---------------------------------------------------------------------------


class TimestampMixin(models.Model):
    """Adds ``created_at`` and ``updated_at``.

    ``auto_now_add`` and ``auto_now`` are set at the database write, not by
    application code, so a row created through the shell, a fixture load or a
    bulk import is stamped identically to one created through the API.
    """

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"


class UUIDMixin(models.Model):
    """Adds a public ``uuid`` alongside the integer primary key.

    The UUID is a *secondary* identifier, deliberately not the primary key.
    A random UUID primary key scatters B-tree inserts across the whole index
    instead of appending to the hot end, which inflates write amplification and
    index size — a real cost on the tables that grow fastest, orders and order
    items. Keeping ``BigAutoField`` as the PK preserves that locality.

    What the UUID buys is that public URLs and API payloads need not expose a
    sequential integer. ``/orders/1042/`` tells any customer roughly how many
    orders the business has taken, and invites them to try 1041.
    """

    uuid = models.UUIDField(
        _("public id"),
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """Queryset whose ``delete()`` marks rows instead of removing them."""

    def delete(self) -> tuple[int, dict[str, int]]:
        """Soft-delete every row in this queryset."""
        count = self.update(is_deleted=True, deleted_at=timezone.now())
        return count, {self.model._meta.label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        """Permanently remove every row in this queryset."""
        return super().delete()

    def alive(self) -> "SoftDeleteQuerySet":
        """Restrict to rows that have not been soft-deleted."""
        return self.filter(is_deleted=False)

    def dead(self) -> "SoftDeleteQuerySet":
        """Restrict to rows that have been soft-deleted."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Default manager that hides soft-deleted rows."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return only rows that are not soft-deleted."""
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Manager that returns every row, deleted or not."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return all rows without filtering."""
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteMixin(models.Model):
    """Adds soft deletion: ``is_deleted``, ``deleted_at`` and two managers.

    ``objects`` excludes deleted rows; ``all_objects`` includes them::

        Product.objects.count()      # visible rows
        Product.all_objects.count()  # including deleted
        product.delete()             # marks the row
        product.hard_delete()        # actually removes it

    Ecommerce needs this because a product referenced by a two-year-old order
    cannot be removed without destroying that order's history, and because
    "undo" is a routine support request.

    Two consequences to design around:

    * ``objects`` is declared first and so becomes ``_default_manager``.
      Related lookups use ``_base_manager``, which is unfiltered, so
      ``order.product`` still resolves for a deleted product. That is the
      intended behaviour — historical orders must still render.
    * A ``unique=True`` field stays unique across deleted rows too. If a slug
      should be reusable after deletion, express it as a ``UniqueConstraint``
      with ``condition=Q(is_deleted=False)`` on the concrete model.
    """

    is_deleted = models.BooleanField(_("deleted"), default=False, db_index=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """Mark this row deleted instead of removing it."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["is_deleted", "deleted_at"])
        return 1, {self._meta.label: 1}

    def hard_delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        """Permanently remove this row from the database."""
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        """Undo a soft delete."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at"])


class SEOFieldsMixin(models.Model):
    """Adds ``slug`` and the meta tags a storefront page needs.

    Length limits mirror what search engines actually render — roughly 60
    characters of title and 160 of description — so the admin form warns an
    editor at the point of entry instead of the text being silently truncated
    in search results.
    """

    slug = models.SlugField(
        _("slug"),
        max_length=SLUG_MAX_LENGTH,
        unique=True,
        db_index=True,
    )
    meta_title = models.CharField(_("meta title"), max_length=70, blank=True)
    meta_description = models.CharField(_("meta description"), max_length=170, blank=True)
    meta_keywords = models.CharField(_("meta keywords"), max_length=255, blank=True)

    class Meta:
        abstract = True

    def get_meta_title(self) -> str:
        """Return the meta title, falling back to the object's own name."""
        return self.meta_title or str(self)


class PublishStatusMixin(models.Model):
    """Adds an editorial workflow: draft, published, archived.

    ``published_at`` is set when the record first goes live and is not cleared
    by a later unpublish, so it remains the canonical "first published" date
    for sitemaps and feeds.

    Deliberately declares no manager, so it composes with
    :class:`SoftDeleteMixin`. Filter explicitly instead::

        Product.objects.filter(**Product.PUBLISHED_FILTER)
    """

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)

    #: Reusable filter kwargs for "visible to the public".
    PUBLISHED_FILTER: dict[str, Any] = {"status": PublishStatus.PUBLISHED}

    class Meta:
        abstract = True

    @property
    def is_published(self) -> bool:
        """Return whether this record is publicly visible."""
        return self.status == PublishStatus.PUBLISHED

    def publish(self, save: bool = True) -> None:
        """Move the record to published, stamping the first publication time."""
        self.status = PublishStatus.PUBLISHED
        if self.published_at is None:
            self.published_at = timezone.now()
        if save:
            self.save(update_fields=["status", "published_at"])

    def unpublish(self, save: bool = True) -> None:
        """Return the record to draft without clearing ``published_at``."""
        self.status = PublishStatus.DRAFT
        if save:
            self.save(update_fields=["status"])

    def archive(self, save: bool = True) -> None:
        """Retire the record from the storefront while keeping its history."""
        self.status = PublishStatus.ARCHIVED
        if save:
            self.save(update_fields=["status"])


class BaseModel(TimestampMixin, UUIDMixin):
    """Timestamps plus a public UUID — the default base for new models.

    Composed here so a concrete model writes ``class Product(BaseModel)``
    rather than repeating the same two mixins everywhere.
    """

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# View mixins
# ---------------------------------------------------------------------------


class OwnedQuerySetMixin:
    """Scope a viewset's queryset to the requesting user.

    Filtering rather than permission-checking is what makes a foreign object
    return 404 instead of 403 — a 403 confirms the row exists, which is itself
    a disclosure. Set ``owner_field`` if the FK is not named ``user``::

        class ReviewViewSet(OwnedQuerySetMixin, ModelViewSet):
            owner_field = "author"
    """

    owner_field: str = "user"

    def get_queryset(self) -> models.QuerySet:
        """Return the parent queryset narrowed to rows the caller owns."""
        queryset = super().get_queryset()

        # drf-spectacular introspects views with an anonymous user while
        # generating the schema; returning empty avoids raising during it.
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()

        user = getattr(self.request, "user", None)
        if not (user and user.is_authenticated):
            return queryset.none()

        return queryset.filter(**{self.owner_field: user})


class SetOwnerOnCreateMixin:
    """Attach the requesting user to newly created objects.

    Keeps the owner out of the request body. A writable owner field lets a
    client create rows in someone else's account by changing one integer.
    """

    owner_field: str = "user"

    def perform_create(self, serializer: Any) -> None:
        """Save with the owner taken from the request, not the payload."""
        serializer.save(**{self.owner_field: self.request.user})


class SoftDeleteViewMixin:
    """Make ``DELETE`` perform a soft delete and return 204.

    Only for viewsets over a model using :class:`SoftDeleteMixin`.
    """

    def perform_destroy(self, instance: Any) -> None:
        """Soft-delete the instance."""
        instance.delete()


class SerializerActionMixin:
    """Choose a serializer per action.

    List and detail views usually want different payloads — a listing needs a
    thumbnail and a price, a detail page needs variants, images and reviews.
    Serving the detail serializer from a list endpoint is a common and
    expensive N+1 source::

        class ProductViewSet(SerializerActionMixin, ModelViewSet):
            serializer_class = ProductDetailSerializer
            serializer_action_classes = {
                "list": ProductListSerializer,
                "create": ProductWriteSerializer,
            }
    """

    serializer_action_classes: dict[str, Any] = {}

    def get_serializer_class(self) -> Any:
        """Return the serializer registered for the current action."""
        action = getattr(self, "action", None)
        return self.serializer_action_classes.get(action) or super().get_serializer_class()
