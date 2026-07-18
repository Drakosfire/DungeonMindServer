"""FastAPI dependencies for the v1 router.

Authentication reuses the shared DungeonBuddy internal-key comparison while
mapping failures into the preliminary typed v1 error envelope.

Constant names mirror ``routers.internal_auth`` so header/env contracts stay
aligned, without importing the ``routers`` package (its ``__init__`` loads
unrelated OAuth routers and credentials).
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Header

from statblocks_v1.api.http_errors import StatblockV1HTTPError
from statblocks_v1.domain.errors import (
    InternalServiceMisconfiguredError,
    UnauthorizedInternalClientError,
)

# Keep identical to routers.internal_auth (shared wire contract).
INTERNAL_KEY_HEADER = "X-DungeonBuddy-Internal-Key"
INTERNAL_KEY_ENV = "DUNGEONBUDDY_INTERNAL_API_KEY"


async def require_internal_service_auth(
    x_dungeonbuddy_internal_key: Annotated[
        str | None,
        Header(alias=INTERNAL_KEY_HEADER),
    ] = None,
) -> None:
    """Require the DungeonBuddy internal API key for all v1 routes."""
    expected_key = os.getenv(INTERNAL_KEY_ENV)
    if not expected_key:
        raise StatblockV1HTTPError(503, InternalServiceMisconfiguredError())

    if x_dungeonbuddy_internal_key is None:
        raise StatblockV1HTTPError(
            401,
            UnauthorizedInternalClientError("Missing internal API key"),
        )

    if not secrets.compare_digest(x_dungeonbuddy_internal_key, expected_key):
        raise StatblockV1HTTPError(
            403,
            UnauthorizedInternalClientError("Invalid internal API key"),
        )
