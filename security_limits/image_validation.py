"""Upload size limits and image magic-byte validation."""

from __future__ import annotations

import io
from typing import Tuple

from fastapi import HTTPException, UploadFile

# 10 MiB hard cap (plan)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Magic sniff — do not trust client Content-Type alone
_MAGIC_PREFIXES: Tuple[Tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # WebP is RIFF....WEBP; checked further below
)


def sniff_image_mime(data: bytes) -> str | None:
    if not data:
        return None
    for prefix, mime in _MAGIC_PREFIXES:
        if data.startswith(prefix):
            if mime == "image/webp":
                if len(data) >= 12 and data[8:12] == b"WEBP":
                    return "image/webp"
                continue
            return mime
    return None


async def read_upload_limited(
    upload: UploadFile,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> Tuple[bytes, str]:
    """
    Read an UploadFile incrementally, aborting above max_bytes.
    Returns (bytes, sniffed_mime). Raises 413/400 on violation.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Upload exceeds maximum size of {max_bytes} bytes",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    mime = sniff_image_mime(data)
    if not mime:
        raise HTTPException(
            status_code=400,
            detail="Upload is not a recognized image (png/jpeg/gif/webp)",
        )
    return data, mime


def validate_image_bytes(data: bytes, max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Upload exceeds maximum size of {max_bytes} bytes",
        )
    mime = sniff_image_mime(data)
    if not mime:
        raise HTTPException(
            status_code=400,
            detail="Upload is not a recognized image (png/jpeg/gif/webp)",
        )
    return mime


def as_upload_file(data: bytes, filename: str, mime: str) -> UploadFile:
    """Rebuild an UploadFile after validation for downstream CF upload."""
    return UploadFile(filename=filename, file=io.BytesIO(data), headers={"content-type": mime})
