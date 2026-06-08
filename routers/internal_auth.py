"""Reusable internal service-to-service authentication dependencies."""

import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException

INTERNAL_KEY_HEADER = "X-DungeonBuddy-Internal-Key"
INTERNAL_KEY_ENV = "DUNGEONBUDDY_INTERNAL_API_KEY"


async def require_dungeonbuddy_internal_key(
    x_dungeonbuddy_internal_key: Annotated[
        str | None,
        Header(alias=INTERNAL_KEY_HEADER),
    ] = None,
) -> None:
    """Require the DungeonBuddy internal API key for protected producer routes."""
    expected_key = os.getenv(INTERNAL_KEY_ENV)
    if not expected_key:
        raise HTTPException(status_code=500, detail="Internal API key is not configured")

    if x_dungeonbuddy_internal_key is None:
        raise HTTPException(status_code=401, detail="Missing internal API key")

    if not secrets.compare_digest(x_dungeonbuddy_internal_key, expected_key):
        raise HTTPException(status_code=403, detail="Invalid internal API key")
