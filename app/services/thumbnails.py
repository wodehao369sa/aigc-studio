"""Server-side image thumbnails.

Thumbnails are generated once, cached on disk under ``media/thumbs/`` and reused.
For a single-user 2C2G host this is cheaper than repeatedly transferring full
resolution results to the browser.
"""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_WIDTH = 480
THUMBNAIL_QUALITY = 82
THUMBNAIL_FORMAT = "JPEG"


def generate_image_thumbnail(data: bytes, max_width: int = THUMBNAIL_MAX_WIDTH) -> bytes | None:
    """Return a JPEG thumbnail, or None when the payload is not a usable image."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                image = Image.alpha_composite(background, rgba)
            image = image.convert("RGB")
            if image.width > max_width:
                height = max(1, round(image.height * max_width / image.width))
                image = image.resize((max_width, height), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format=THUMBNAIL_FORMAT, quality=THUMBNAIL_QUALITY, optimize=True)
            return buffer.getvalue()
    except Exception:  # noqa: BLE001 - never let a thumbnail break the page
        logger.warning("thumbnail generation failed", exc_info=True)
        return None
