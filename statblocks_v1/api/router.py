"""DungeonBuddy-facing internal router for statblock contract v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import require_internal_service_auth

router = APIRouter(
    prefix="/api/internal/dungeonbuddy/v1",
    tags=["DungeonBuddy Statblocks v1"],
    dependencies=[Depends(require_internal_service_auth)],
)


@router.get("/statblocks/health")
async def health() -> dict[str, object]:
    """Foundation capability discovery. No generation or persistence yet."""
    return {
        "status": "foundation",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "capabilities": [],
    }
