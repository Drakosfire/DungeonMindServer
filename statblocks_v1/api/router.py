"""DungeonBuddy-facing internal router for statblock contract v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import require_internal_service_auth
from statblocks_v1.api.models import ErrorEnvelopeV1, HealthResponseV1

_AUTH_ERROR_RESPONSES = {
    401: {"model": ErrorEnvelopeV1, "description": "Missing internal API key"},
    403: {"model": ErrorEnvelopeV1, "description": "Invalid internal API key"},
    503: {
        "model": ErrorEnvelopeV1,
        "description": "Internal service misconfigured (missing API key env)",
    },
}

router = APIRouter(
    prefix="/api/internal/dungeonbuddy/v1",
    tags=["DungeonBuddy Statblocks v1"],
    dependencies=[Depends(require_internal_service_auth)],
    responses=_AUTH_ERROR_RESPONSES,
)


@router.get(
    "/statblocks/health",
    response_model=HealthResponseV1,
    responses=_AUTH_ERROR_RESPONSES,
)
async def health() -> HealthResponseV1:
    """Foundation capability discovery. No generation or persistence yet."""
    return HealthResponseV1(
        status="foundation",
        contract=CONTRACT_NAME,
        contract_version=CONTRACT_VERSION,
        capabilities=[],
    )
