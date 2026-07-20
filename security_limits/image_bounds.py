"""
Bounded image open for export/composite — mitigate decompression bombs.
"""

from __future__ import annotations

import io
import logging

from fastapi import HTTPException
from PIL import Image

logger = logging.getLogger(__name__)

# Hard ceilings for decoded images (map export / composite)
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 25_000_000  # ~25 megapixels

# Treat Pillow decompression-bomb path as hard error
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def open_image_bounded(data: bytes) -> Image.Image:
    """
    Open an image and reject oversized width/height/pixel counts before
    full decompress/composite work.
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()  # force decode under MAX_IMAGE_PIXELS
    except Image.DecompressionBombError as e:
        logger.warning("Rejected decompression bomb: %s", type(e).__name__)
        raise HTTPException(
            status_code=413,
            detail="Image exceeds maximum decoded pixel budget",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid image data") from e

    width, height = img.size
    if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image dimensions {width}x{height} exceed maximum "
                f"{MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}"
            ),
        )
    if width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds maximum decoded pixel budget",
        )
    return img
