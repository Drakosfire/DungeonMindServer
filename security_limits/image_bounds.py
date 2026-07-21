"""
Bounded image open for export/composite — mitigate decompression bombs.
"""

from __future__ import annotations

import base64
import binascii
import io
import logging
import re

from fastapi import HTTPException
from PIL import Image

from security_limits.image_validation import MAX_UPLOAD_BYTES, validate_image_bytes

logger = logging.getLogger(__name__)

# Hard ceilings for decoded images (map export / composite / inpaint)
MAX_IMAGE_WIDTH = 8192
MAX_IMAGE_HEIGHT = 8192
MAX_IMAGE_PIXELS = 25_000_000  # ~25 megapixels

# Encoded data-URI cap (~4/3 of decoded byte cap + header slack)
MAX_DATA_URI_CHARS = (MAX_UPLOAD_BYTES * 4 // 3) + 128

_DATA_URI_RE = re.compile(
    r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$",
    re.IGNORECASE,
)

# Treat Pillow decompression-bomb path as hard error
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def _reject_oversized(width: int, height: int) -> None:
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


def open_image_bounded(data: bytes) -> Image.Image:
    """
    Open an image and reject oversized width/height/pixel counts *before*
    forcing a full pixel decode via load().
    """
    try:
        img = Image.open(io.BytesIO(data))
        # Header size is available without full decompress for common formats
        width, height = img.size
        _reject_oversized(width, height)
        img.load()  # force decode under Image.MAX_IMAGE_PIXELS
    except HTTPException:
        raise
    except Image.DecompressionBombError as e:
        logger.warning("Rejected decompression bomb: %s", type(e).__name__)
        raise HTTPException(
            status_code=413,
            detail="Image exceeds maximum decoded pixel budget",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid image data") from e

    # Re-check after load in case format lied about dimensions
    width, height = img.size
    _reject_oversized(width, height)
    return img


def decode_data_uri_bounded(data_uri: str, *, field: str = "image") -> Image.Image:
    """
    Strictly validate a data:image/...;base64,... URI, cap encoded/decoded
    size, and open via open_image_bounded.
    """
    if not data_uri or not isinstance(data_uri, str):
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if len(data_uri) > MAX_DATA_URI_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"{field} exceeds maximum encoded size",
        )
    if not data_uri.startswith("data:image/"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field} format: must be base64-encoded image",
        )
    match = _DATA_URI_RE.match(data_uri.strip())
    if not match:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field} format: expected data:image/...;base64,...",
        )
    b64_payload = match.group(2).replace("\n", "").replace("\r", "").replace(" ", "")
    # Normalize padding for strict validate=True decode
    pad = (-len(b64_payload)) % 4
    if pad:
        b64_payload += "=" * pad
    try:
        raw = base64.b64decode(b64_payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}: base64 decode failed",
        ) from e

    validate_image_bytes(raw, max_bytes=MAX_UPLOAD_BYTES)
    return open_image_bounded(raw)


def encode_image_data_uri(image: Image.Image, fmt: str = "PNG") -> str:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/{fmt.lower()};base64,{b64}"
