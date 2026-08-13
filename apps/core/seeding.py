"""Placeholder image generation for seed commands.

Seed data needs real image files, not just rows: ``ProductImage.image`` and
``Banner.image`` carry validators with minimum dimensions, and a listing page
seeded with empty image fields tells you nothing about whether the grid works.

Images are generated rather than downloaded. A seed command that reaches the
network fails on an air-gapped CI box, takes minutes instead of seconds, and
makes the fixture depend on someone else's uptime.

Deterministic: the same ``seed`` produces the same colours, so re-running a
seed does not reshuffle the catalogue's appearance.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

from django.core.files.base import ContentFile

#: Muted, fashion-appropriate palette. Random RGB produces neon greens that
#: make a seeded storefront look broken rather than empty.
PALETTE: tuple[tuple[int, int, int], ...] = (
    (198, 174, 156), (161, 141, 132), (122, 116, 122), (94, 106, 116),
    (176, 141, 122), (144, 122, 110), (110, 122, 108), (203, 190, 174),
    (156, 126, 134), (128, 138, 150), (186, 160, 140), (100, 96, 104),
)


def _colour_for(token: str, offset: int = 0) -> tuple[int, int, int]:
    """Return a stable palette colour for ``token``.

    Hashed rather than random so a product keeps its colour across re-runs —
    a seeded catalogue that changes appearance on every run is impossible to
    eyeball for regressions.
    """
    digest = hashlib.md5(f"{token}:{offset}".encode()).digest()
    return PALETTE[digest[0] % len(PALETTE)]


def make_image(
    label: str,
    *,
    width: int = 900,
    height: int = 1200,
    offset: int = 0,
    caption: str = "",
) -> ContentFile:
    """Return a JPEG placeholder sized ``width`` × ``height``.

    Defaults to 3:4 portrait at 900×1200, which clears the 400×600 floor
    ``validate_product_image`` enforces. Banners need a wide crop and pass
    their own dimensions.

    Falls back to a solid rectangle if the default font is unavailable —
    Pillow ships one, but a stripped container image sometimes does not.
    """
    from PIL import Image, ImageDraw

    base = _colour_for(label, offset)
    image = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(image)

    # A lighter inset panel, so the placeholder reads as deliberate rather
    # than as a failed upload.
    inset = min(width, height) // 12
    lighter = tuple(min(255, channel + 26) for channel in base)
    draw.rectangle(
        [inset, inset, width - inset, height - inset], fill=lighter
    )

    text = caption or label
    try:
        from PIL import ImageFont

        font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((width - (box[2] - box[0])) / 2, (height - (box[3] - box[1])) / 2),
            text,
            fill=(255, 255, 255),
            font=font,
        )
    except Exception:  # noqa: BLE001 - a fontless build still gets a usable image
        pass

    buffer = io.BytesIO()
    # quality=70 keeps 150 products × 5 images comfortably under a few hundred
    # megabytes of seeded media.
    image.save(buffer, format="JPEG", quality=70, optimize=True)

    stem = "".join(c if c.isalnum() else "-" for c in label.lower())[:40]
    return ContentFile(buffer.getvalue(), name=f"{stem}-{offset}.jpg")


def make_banner_image(label: str, *, mobile: bool = False, offset: int = 0) -> ContentFile:
    """Return a banner-shaped placeholder.

    Two aspect ratios, because ``Banner`` stores separate desktop and mobile
    crops. Both clear the 1200×300 floor ``validate_banner_image`` enforces —
    the portrait crop is 1200 wide and taller, not narrower.
    """
    if mobile:
        return make_image(label, width=1200, height=1500, offset=offset + 100)
    return make_image(label, width=2400, height=800, offset=offset)
