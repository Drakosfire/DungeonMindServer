"""Privacy-preserving structured request telemetry for statblock v1."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from uuid import uuid4

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"
logger = logging.getLogger("statblocks_v1")


def safe_fields(**fields: object) -> dict[str, object]:
    """Drop payload/secrets and retain scalar operational identifiers only."""
    forbidden = {"api_key", "authorization", "prompt", "definition", "payload", "internal_key"}
    return {
        key: value
        for key, value in fields.items()
        if key.lower() not in forbidden and value is not None
    }


V1_PATH_PREFIX = "/api/internal/dungeonbuddy/v1"


async def request_observability(request: Request, call_next: Callable[[Request], Response]) -> Response:
    if not request.url.path.startswith(V1_PATH_PREFIX):
        return await call_next(request)
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
    request.state.request_id = request_id
    started = time.monotonic()
    response: Response
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("statblocks_v1_request %s", safe_fields(
            request_id=request_id, route=request.url.path, outcome_code="unhandled_error",
            latency_ms=int((time.monotonic() - started) * 1000),
        ))
        raise
    response.headers[REQUEST_ID_HEADER] = request_id
    logger.info("statblocks_v1_request %s", safe_fields(
        request_id=request_id,
        route=request.url.path,
        method=request.method,
        status_code=response.status_code,
        outcome_code="success" if response.status_code < 400 else "http_error",
        latency_ms=int((time.monotonic() - started) * 1000),
    ))
    return response
