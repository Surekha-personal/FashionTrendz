"""Catalog helpers: upload paths and slug generation.

Slug generation delegates to :func:`apps.core.utils.generate_unique_slug`; the
wrappers here only decide what text each model slugs *from*.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils.deconstruct import deconstructible

from apps.core.utils import generate_unique_slug

if TYPE_CHECKING:  # pragma: no cover - typing only
    from apps.catalog.models import Category


@deconstructible
class UploadPath:
    """Build a collision-proof ``upload_to`` callable for a media sub-folder.

    Declared as a ``@deconstructible`` class rather than one function per image
    field. Migrations must serialise ``upload_to``, which rules out lambdas and
    partials; a deconstructible class serialises as
    ``UploadPath('catalog/categories/banner')`` and keeps eleven near-identical
    functions out of this module.

    The stored filename is a UUID, never the uploaded one. Trusting the client
    filename lets one upload overwrite another by colliding on a name, and
    invites path traversal through crafted names.
    """

    def __init__(self, folder: str) -> None:
        self.folder = folder.strip("/")

    def __call__(self, instance: models.Model, filename: str) -> str:
        """Return the storage path for ``filename``."""
        suffix = Path(filename).suffix.lower()
        return f"{self.folder}/{uuid.uuid4().hex}{suffix}"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, UploadPath) and self.folder == other.folder

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"UploadPath({self.folder!r})"


# Instantiated at module level so migrations reference a stable object.
category_icon_path = UploadPath("catalog/categories/icons")
category_image_path = UploadPath("catalog/categories/images")
category_banner_path = UploadPath("catalog/categories/banners")
category_menu_path = UploadPath("catalog/categories/menu")

subcategory_image_path = UploadPath("catalog/subcategories/images")
subcategory_banner_path = UploadPath("catalog/subcategories/banners")

brand_logo_path = UploadPath("catalog/brands/logos")
brand_banner_path = UploadPath("catalog/brands/banners")

collection_image_path = UploadPath("catalog/collections/images")
collection_banner_path = UploadPath("catalog/collections/banners")


# ---------------------------------------------------------------------------
# Slugs
# ---------------------------------------------------------------------------


def build_category_slug(name: str, instance_pk: Any = None) -> str:
    """Return a unique slug for a category, derived from its name."""
    from apps.catalog.models import Category

    return generate_unique_slug(Category, name, instance_pk=instance_pk)


def build_subcategory_slug(
    category: "Category",
    name: str,
    instance_pk: Any = None,
) -> str:
    """Return a unique slug for a subcategory, scoped by its parent's name.

    Slugs are globally unique rather than unique-per-category, so the URL
    ``/subcategories/{slug}/`` needs no parent segment to resolve. Prefixing
    the parent name is what makes that practical: "Shirts" under both Men and
    Women becomes ``men-shirts`` and ``women-shirts`` — readable and
    SEO-meaningful — instead of ``shirts`` and a random-suffixed ``shirts-a3f9``.
    """
    from apps.catalog.models import SubCategory

    source = f"{category.name} {name}" if category is not None else name
    return generate_unique_slug(SubCategory, source, instance_pk=instance_pk)


def build_brand_slug(name: str, instance_pk: Any = None) -> str:
    """Return a unique slug for a brand, derived from its name."""
    from apps.catalog.models import Brand

    return generate_unique_slug(Brand, name, instance_pk=instance_pk)


def build_collection_slug(title: str, instance_pk: Any = None) -> str:
    """Return a unique slug for a collection, derived from its title."""
    from apps.catalog.models import Collection

    return generate_unique_slug(Collection, title, instance_pk=instance_pk)
