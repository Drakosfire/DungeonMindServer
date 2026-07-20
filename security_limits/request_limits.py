"""
Request body size limits (defense in depth alongside nginx client_max_body_size).

Production nginx (dungeonmind.net) sets client_max_body_size 10M. This middleware
rejects oversized Content-Length early when the app is reached without that edge
limit (local, misconfigured proxy, or TestClient).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

# Align with nginx/dungeonmind.net client_max_body_size 10M
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


async def limit_request_body_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body exceeds maximum size of "
                            f"{MAX_REQUEST_BODY_BYTES} bytes"
                        )
                    },
                )
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid Content-Length header"},
            )
    return await call_next(request)
