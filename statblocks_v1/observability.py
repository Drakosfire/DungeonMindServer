"""Privacy-preserving structured request telemetry for statblock v1."""
from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"
V1_PATH_PREFIX = "/api/internal/dungeonbuddy/v1"
logger = logging.getLogger("statblocks_v1")

_FORBIDDEN = frozenset(
    {
        "api_key",
        "authorization",
        "prompt",
        "definition",
        "payload",
        "internal_key",
        "description",
        "source_description",
    }
)


def safe_fields(**fields: object) -> dict[str, object]:
    """Drop payload/secrets and retain scalar operational identifiers only."""
    return {
        key: value
        for key, value in fields.items()
        if key.lower() not in _FORBIDDEN and value is not None
    }


def bind_request_fields(request: Request, **fields: object) -> None:
    """Attach scalar operational fields for the middleware to emit after the response."""
    bucket: dict[str, object] = getattr(request.state, "statblocks_v1_fields", {})
    bucket.update(safe_fields(**fields))
    request.state.statblocks_v1_fields = bucket


def bind_outcome(request: Request, outcome_code: str, **fields: object) -> None:
    bind_request_fields(request, outcome_code=outcome_code, **fields)


def log_operation(operation: str, **fields: object) -> None:
    """Emit an operation-scoped structured log line (no payloads/secrets)."""
    logger.info("statblocks_v1_operation %s", safe_fields(operation=operation, **fields))


async def request_observability(
    request: Request, call_next: Callable[[Request], Response]
) -> Response:
    if not request.url.path.startswith(V1_PATH_PREFIX):
        return await call_next(request)
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
    request.state.request_id = request_id
    request.state.statblocks_v1_fields = {"request_id": request_id}
    started = time.monotonic()
    response: Response
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "statblocks_v1_request %s",
            safe_fields(
                request_id=request_id,
                route=request.url.path,
                method=request.method,
                outcome_code="unhandled_error",
                latency_ms=int((time.monotonic() - started) * 1000),
            ),
        )
        raise
    response.headers[REQUEST_ID_HEADER] = request_id
    bound: Mapping[str, Any] = getattr(request.state, "statblocks_v1_fields", {})
    outcome = bound.get("outcome_code")
    if outcome is None:
        outcome = "success" if response.status_code < 400 else "http_error"
    logger.info(
        "statblocks_v1_request %s",
        safe_fields(
            request_id=request_id,
            route=request.url.path,
            method=request.method,
            status_code=response.status_code,
            outcome_code=outcome,
            latency_ms=int((time.monotonic() - started) * 1000),
            **{k: v for k, v in bound.items() if k not in {"request_id", "outcome_code"}},
        ),
    )
    return response
