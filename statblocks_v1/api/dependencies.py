"""FastAPI dependencies for the v1 router.

Authentication reuses the shared DungeonBuddy internal-key comparison while
mapping failures into the preliminary typed v1 error envelope.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated, Any

from fastapi import Header, HTTPException

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER
from statblocks_v1.domain.errors import (
    InternalServiceMisconfiguredError,
    UnauthorizedInternalClientError,
)


def _error_body(error: UnauthorizedInternalClientError | InternalServiceMisconfiguredError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
        }
    }
    if error.details:
        body["error"]["details"] = error.details
    return body


async def require_internal_service_auth(
    x_dungeonbuddy_internal_key: Annotated[
        str | None,
        Header(alias=INTERNAL_KEY_HEADER),
    ] = None,
) -> None:
    """Require the DungeonBuddy internal API key for all v1 routes."""
    expected_key = os.getenv(INTERNAL_KEY_ENV)
    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail=_error_body(InternalServiceMisconfiguredError()),
        )

    if x_dungeonbuddy_internal_key is None:
        raise HTTPException(
            status_code=401,
            detail=_error_body(UnauthorizedInternalClientError("Missing internal API key")),
        )

    if not secrets.compare_digest(x_dungeonbuddy_internal_key, expected_key):
        raise HTTPException(
            status_code=403,
            detail=_error_body(UnauthorizedInternalClientError("Invalid internal API key")),
        )
