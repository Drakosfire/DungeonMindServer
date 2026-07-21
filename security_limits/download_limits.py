"""
CDN host allowlists and bounded download helpers (SSRF + DoS).
"""

from __future__ import annotations

from typing import Iterable, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

DOWNLOAD_ALLOWED_HOST_SUFFIXES: Tuple[str, ...] = (
    "imagedelivery.net",
    "r2.cloudflarestorage.com",
    "cloudflarestorage.com",
    "r2.dev",
)

ALLOWED_PROXY_CONTENT_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
    }
)

MAX_PROXY_BYTES = 25 * 1024 * 1024


def download_url_allowed(
    url: str,
    allowed_suffixes: Iterable[str] = DOWNLOAD_ALLOWED_HOST_SUFFIXES,
) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    return any(host == suffix or host.endswith("." + suffix) for suffix in allowed_suffixes)


async def fetch_allowlisted_bytes(
    url: str,
    *,
    max_bytes: int = MAX_PROXY_BYTES,
    timeout: float = 60.0,
) -> Tuple[bytes, str]:
    """
    Stream an allowlisted HTTPS URL into memory with hard size and type caps.
    Returns (content, content_type).
    """
    if not download_url_allowed(url):
        raise HTTPException(status_code=400, detail="URL host is not allowlisted")

    headers_out_type = "image/png"
    buf = bytearray()

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "image/png").split(";")[0].strip().lower()
            if content_type not in ALLOWED_PROXY_CONTENT_TYPES:
                raise HTTPException(
                    status_code=502,
                    detail=f"Upstream content-type not allowed: {content_type}",
                )
            headers_out_type = content_type

            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Upstream object exceeds maximum size of {max_bytes} bytes",
                        )
                except ValueError:
                    pass

            async for chunk in response.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upstream object exceeds maximum size of {max_bytes} bytes",
                    )

    return bytes(buf), headers_out_type
