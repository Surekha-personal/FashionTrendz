"""Image resolution for seed commands.

Seed images come from real files supplied by the content team, never from
generated placeholders. Two ways to supply them, checked in this order:

1. **A manifest** — ``seed_assets/manifest.json`` or ``manifest.csv``, mapping a
   product SKU or slug to an ordered list of image files. Use this when the
   photography is already named and catalogued.

2. **Folder convention** — ``seed_assets/products/<subcategory-slug>/*.jpg``,
   falling back to ``seed_assets/products/_default/``. Use this when the team
   just wants to drop a hundred shirt photographs into a folder called
   ``shirts`` and be done.

If neither yields a file the image is **skipped with a warning**, not faked.
A catalogue with visibly missing imagery is a problem someone fixes; a
catalogue full of grey rectangles is one everybody learns to ignore.

Nothing here writes a URL into the database. ``ProductImage.image`` is an
``ImageField``: Django copies the file into ``MEDIA_ROOT`` under the model's
``upload_to`` and stores the resulting relative path, so the API keeps
returning the same absolute URLs it always has. Remote entries in a manifest
are downloaded to disk first, and only with ``--fetch-remote``.
"""

from __future__ import annotations

import csv
import json
import logging
import pathlib
import random
from typing import Any, Iterable, Iterator
from urllib.parse import urlparse

from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

#: Extensions the resolver will pick up from a folder scan.
IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif"})

#: Folder searched when a subcategory has no dedicated directory.
FALLBACK_DIR = "_default"

#: Ceiling on a downloaded file, so a mistyped manifest URL pointing at a video
#: cannot fill the disk.
MAX_REMOTE_BYTES = 12 * 1024 * 1024


def default_assets_dir() -> pathlib.Path:
    """Return the configured asset root.

    Overridable with ``SEED_ASSETS_DIR`` in settings or the environment, so CI
    can point at a small fixture set and a content machine at the real library.
    """
    configured = getattr(settings, "SEED_ASSETS_DIR", "")
    if configured:
        return pathlib.Path(configured)
    return pathlib.Path(settings.BASE_DIR) / "seed_assets"


class AssetLibrary:
    """Resolves image files for seeded records.

    One instance per command run. Directory listings are cached, because a
    five-hundred-product seed would otherwise stat the same folders thousands
    of times.
    """

    def __init__(
        self,
        root: pathlib.Path | str | None = None,
        *,
        fetch_remote: bool = False,
        rng: random.Random | None = None,
    ) -> None:
        self.root = pathlib.Path(root) if root else default_assets_dir()
        self.fetch_remote = fetch_remote
        self.rng = rng or random.Random()

        self._dir_cache: dict[pathlib.Path, list[pathlib.Path]] = {}
        self._manifest: dict[str, list[str]] = {}
        self._manifest_source = ""
        self.missing: set[str] = set()
        self.resolved_count = 0
        self.remote_count = 0

        self._load_manifest()

    # -- Manifest -----------------------------------------------------------

    def _load_manifest(self) -> None:
        """Read ``manifest.json`` or ``manifest.csv`` if either is present."""
        for name, reader in (("manifest.json", self._read_json),
                             ("manifest.csv", self._read_csv)):
            path = self.root / name
            if path.is_file():
                try:
                    self._manifest = reader(path)
                    self._manifest_source = str(path)
                except Exception as exc:  # noqa: BLE001 - report, do not abort
                    logger.warning("could not read %s: %s", path, exc)
                else:
                    return

    @staticmethod
    def _read_json(path: pathlib.Path) -> dict[str, list[str]]:
        """Parse a JSON manifest.

        Accepts either ``{"SKU": ["a.jpg", "b.jpg"]}`` or the more verbose
        ``{"products": [{"sku": "...", "images": [...]}]}``, because both shapes
        turn up depending on which tool exported the sheet.
        """
        data = json.loads(path.read_text(encoding="utf-8"))

        if isinstance(data, dict) and "products" in data:
            return {
                str(row.get("sku") or row.get("slug", "")).strip(): list(
                    row.get("images", [])
                )
                for row in data["products"]
                if row.get("sku") or row.get("slug")
            }

        return {
            str(key).strip(): ([value] if isinstance(value, str) else list(value))
            for key, value in dict(data).items()
        }

    @staticmethod
    def _read_csv(path: pathlib.Path) -> dict[str, list[str]]:
        """Parse a CSV manifest of ``sku,image,display_order``.

        One row per image rather than a comma-joined cell: a spreadsheet is the
        tool the content team actually uses, and quoting a list inside one cell
        is where those exports go wrong.
        """
        out: dict[str, list[tuple[int, str]]] = {}
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                key = (row.get("sku") or row.get("slug") or "").strip()
                image = (row.get("image") or row.get("file") or "").strip()
                if not key or not image:
                    continue
                try:
                    order = int(row.get("display_order") or 0)
                except ValueError:
                    order = 0
                out.setdefault(key, []).append((order, image))

        return {
            key: [image for _, image in sorted(entries)]
            for key, entries in out.items()
        }

    @property
    def has_manifest(self) -> bool:
        """Return whether a manifest was loaded."""
        return bool(self._manifest)

    @property
    def manifest_source(self) -> str:
        """Return the manifest path, for the command's summary line."""
        return self._manifest_source

    # -- Resolution ---------------------------------------------------------

    def _listing(self, directory: pathlib.Path) -> list[pathlib.Path]:
        """Return the sorted image files in ``directory``, cached."""
        if directory not in self._dir_cache:
            if directory.is_dir():
                self._dir_cache[directory] = sorted(
                    path
                    for path in directory.iterdir()
                    if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
                )
            else:
                self._dir_cache[directory] = []
        return self._dir_cache[directory]

    def _resolve_entry(self, entry: str) -> File | None:
        """Turn one manifest entry — a path or a URL — into an open file."""
        if entry.startswith(("http://", "https://")):
            return self._fetch(entry)

        path = pathlib.Path(entry)
        if not path.is_absolute():
            path = self.root / path
        if path.is_file():
            return File(path.open("rb"), name=path.name)

        self.missing.add(entry)
        return None

    def _fetch(self, url: str) -> File | None:
        """Download a remote image into memory.

        Off unless ``--fetch-remote`` is passed. A seed command that reaches the
        network by default fails on an air-gapped CI box and makes the fixture
        depend on somebody else's uptime.
        """
        if not self.fetch_remote:
            self.missing.add(f"{url} (remote; pass --fetch-remote)")
            return None

        import urllib.request

        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": "fashion-trendz-seed/1.0"}
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = response.read(MAX_REMOTE_BYTES + 1)
        except Exception as exc:  # noqa: BLE001 - one bad URL must not stop a seed
            logger.warning("could not fetch %s: %s", url, exc)
            self.missing.add(url)
            return None

        if len(payload) > MAX_REMOTE_BYTES:
            logger.warning("%s exceeds %d bytes, skipped", url, MAX_REMOTE_BYTES)
            self.missing.add(url)
            return None

        name = pathlib.Path(urlparse(url).path).name or "remote.jpg"
        self.remote_count += 1
        return ContentFile(payload, name=name)

    def images_for_product(
        self,
        *,
        sku: str,
        slug: str = "",
        subcategory_slug: str = "",
        count: int = 5,
    ) -> list[File]:
        """Return up to ``count`` open image files for one product.

        Manifest first, then the subcategory folder, then ``_default``. Returns
        an empty list when nothing is available — the caller decides whether to
        warn or carry on.
        """
        for key in (sku, slug):
            if key and key in self._manifest:
                files = [
                    handle
                    for entry in self._manifest[key][:count]
                    if (handle := self._resolve_entry(entry)) is not None
                ]
                if files:
                    self.resolved_count += len(files)
                    return files

        for folder in (subcategory_slug, FALLBACK_DIR):
            if not folder:
                continue
            listing = self._listing(self.root / "products" / folder)
            if not listing:
                continue

            # Deterministic per product, so a re-run does not reshuffle which
            # photograph is the primary image.
            picker = random.Random(f"{sku}:{folder}")
            chosen = (
                picker.sample(listing, k=count)
                if len(listing) >= count
                else [listing[i % len(listing)] for i in range(count)]
            )
            files = [File(path.open("rb"), name=path.name) for path in chosen]
            self.resolved_count += len(files)
            return files

        self.missing.add(f"products/{subcategory_slug or FALLBACK_DIR}/")
        return []

    def image_for(self, *, folder: str, key: str) -> File | None:
        """Return one image from ``seed_assets/<folder>/``.

        Used by banners, brand logos, category art and review photographs —
        anything that needs a single file rather than a gallery.
        """
        listing = self._listing(self.root / folder)
        if not listing:
            self.missing.add(f"{folder}/")
            return None

        picker = random.Random(f"{folder}:{key}")
        path = picker.choice(listing)
        self.resolved_count += 1
        return File(path.open("rb"), name=path.name)

    def images_from(self, folder: str, *, key: str, count: int) -> list[File]:
        """Return ``count`` images from ``seed_assets/<folder>/``."""
        listing = self._listing(self.root / folder)
        if not listing:
            self.missing.add(f"{folder}/")
            return []

        picker = random.Random(f"{folder}:{key}")
        chosen = (
            picker.sample(listing, k=count)
            if len(listing) >= count
            else [listing[i % len(listing)] for i in range(count)]
        )
        self.resolved_count += len(chosen)
        return [File(path.open("rb"), name=path.name) for path in chosen]

    # -- Reporting ----------------------------------------------------------

    def summary(self) -> str:
        """Return a one-line description of what the library found."""
        if self.has_manifest:
            source = f"manifest {self._manifest_source} ({len(self._manifest)} keys)"
        elif self.root.is_dir():
            source = f"folder {self.root}"
        else:
            source = f"{self.root} (missing)"
        remote = f", {self.remote_count} downloaded" if self.remote_count else ""
        return f"{source}: {self.resolved_count} image(s) resolved{remote}"

    def warnings(self, limit: int = 8) -> list[str]:
        """Return the distinct lookups that found nothing."""
        return sorted(self.missing)[:limit]


def close_all(files: Iterable[File]) -> None:
    """Close open file handles.

    A five-hundred-product seed opens thousands of files; leaving them to the
    garbage collector exhausts the process file-descriptor limit long before it
    finishes.
    """
    for handle in files:
        try:
            handle.close()
        except Exception:  # noqa: BLE001 - closing twice is not an error worth raising
            pass


def iter_expected_folders(subcategory_slugs: Iterable[str]) -> Iterator[str]:
    """Yield the folder layout the content team is expected to populate."""
    yield "products/_default/"
    for slug in sorted(set(subcategory_slugs)):
        yield f"products/{slug}/"
    for folder in ("banners/hero", "banners/strip", "banners/category",
                   "banners/sale", "brands", "categories", "reviews"):
        yield f"{folder}/"
