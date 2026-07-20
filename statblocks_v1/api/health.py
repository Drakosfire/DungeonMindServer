"""Liveness, readiness, and capability endpoints for statblock v1."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import require_internal_service_auth
from statblocks_v1.api.models import ErrorEnvelopeV1, HealthResponseV1
from statblocks_v1.config import ConfigurationError, StatblocksV1Settings

CAPABILITIES = (
    "candidate_generate",
    "candidate_revise",
    "definition_validate",
    "candidate_read",
    "statblock_create",
    "statblock_revision_append",
    "statblock_read",
    "statblock_revision_list",
    "statblock_revision_read",
)
GENERATION_CAPABILITIES = {"candidate_generate", "candidate_revise"}

_AUTH_ERROR_RESPONSES = {
    401: {"model": ErrorEnvelopeV1, "description": "Missing internal API key"},
    403: {"model": ErrorEnvelopeV1, "description": "Invalid internal API key"},
    503: {
        "model": ErrorEnvelopeV1,
        "description": "Internal service misconfigured",
    },
}

liveness_router = APIRouter(
    prefix="/api/internal/dungeonbuddy/v1",
    tags=["DungeonBuddy Statblocks v1"],
)
health_router = APIRouter(
    prefix="/api/internal/dungeonbuddy/v1",
    tags=["DungeonBuddy Statblocks v1"],
    dependencies=[Depends(require_internal_service_auth)],
    responses=_AUTH_ERROR_RESPONSES,
)


@liveness_router.get("/statblocks/health/live", operation_id="statblocks_v1_liveness")
async def liveness() -> dict[str, str]:
    """Process-level health: no secrets or dependency probes."""
    return {"status": "live"}


def _capabilities(settings: StatblocksV1Settings | None) -> list[str]:
    if settings is None or settings.feature_enabled:
        return list(CAPABILITIES)
    return [capability for capability in CAPABILITIES if capability not in GENERATION_CAPABILITIES]


def _settings_or_none() -> StatblocksV1Settings | None:
    try:
        return StatblocksV1Settings.from_environment()
    except ConfigurationError:
        return None


@health_router.get(
    "/statblocks/health",
    response_model=HealthResponseV1,
    responses=_AUTH_ERROR_RESPONSES,
    operation_id="statblocks_v1_capabilities",
)
async def capabilities() -> HealthResponseV1:
    """Authenticated contract discovery; never exposes configuration values."""
    settings = _settings_or_none()
    return HealthResponseV1(
        status="available" if settings is not None else "misconfigured",
        contract=CONTRACT_NAME,
        contract_version=CONTRACT_VERSION,
        capabilities=_capabilities(settings),
    )


@health_router.get("/statblocks/health/ready", operation_id="statblocks_v1_readiness")
async def readiness() -> JSONResponse:
    """Configuration readiness, not an invasive provider availability probe."""
    try:
        settings = StatblocksV1Settings.from_environment()
    except ConfigurationError as error:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "contract": CONTRACT_NAME,
                "errors": ["configuration_invalid"],
                "detail": str(error),
            },
        )
    errors = settings.readiness_errors()
    payload = {
        "status": "ready" if not errors else "not_ready",
        "contract": CONTRACT_NAME,
        "generation_enabled": settings.feature_enabled,
        "read_routes_enabled": settings.firestore_enabled
        and (settings.feature_enabled or settings.allow_reads_when_disabled),
        "errors": errors,
    }
    return JSONResponse(status_code=200 if not errors else 503, content=payload)
