"""
Request body size limits (defense in depth alongside nginx client_max_body_size).

Production nginx (dungeonmind.net) sets client_max_body_size 10M. The backend
must also count streamed (chunked) bodies — Content-Length alone is bypassable.

Deployment contract: publish the API only on loopback
(`127.0.0.1:7860:7860` / `-p 127.0.0.1:7860:7860`) so Nginx is the sole
external entry point.
"""

from __future__ import annotations

import logging

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

# Align with nginx/dungeonmind.net client_max_body_size 10M
MAX_REQUEST_BODY_BYTES = 10 * 1024 * 1024


class BodyTooLargeError(Exception):
    """Raised when streamed body exceeds MAX_REQUEST_BODY_BYTES."""


class MaxBodySizeASGIMiddleware:
    """
    Pure ASGI middleware: reject oversized Content-Length early, and count
    actual http.request body bytes for chunked / missing-length requests.
    """

    def __init__(self, app: ASGIApp, max_body_size: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await _send_json(send, 400, {"detail": "Invalid Content-Length header"})
                return
            if declared > self.max_body_size:
                await _send_json(
                    send,
                    413,
                    {
                        "detail": (
                            f"Request body exceeds maximum size of "
                            f"{self.max_body_size} bytes"
                        )
                    },
                )
                return

        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"") or b""
                received += len(chunk)
                if received > self.max_body_size:
                    raise BodyTooLargeError()
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except BodyTooLargeError:
            if response_started:
                logger.warning(
                    "Body exceeded limit after response started; closing connection"
                )
                raise
            await _send_json(
                send,
                413,
                {
                    "detail": (
                        f"Request body exceeds maximum size of "
                        f"{self.max_body_size} bytes"
                    )
                },
            )


async def _send_json(send: Send, status: int, payload: dict) -> None:
    import json

    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


# Back-compat alias used by older tests / imports
async def limit_request_body_middleware(request, call_next):
    """
    Deprecated BaseHTTPMiddleware-style helper kept for unit tests that only
    exercise Content-Length rejection. Prefer MaxBodySizeASGIMiddleware.
    """
    from fastapi.responses import JSONResponse

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
