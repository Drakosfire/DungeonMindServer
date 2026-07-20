"""Liveness, readiness, and capability endpoints for statblock v1."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import require_internal_service_auth
from statblocks_v1.api.models import ErrorEnvelopeV1, HealthResponseV1, ReadinessResponseV1
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
GENERATION_CAPABILITIES = frozenset({"candidate_generate", "candidate_revise"})
PERSISTENCE_CAPABILITIES = frozenset(
    {
        "candidate_read",
        "statblock_create",
        "statblock_revision_append",
        "statblock_read",
        "statblock_revision_list",
        "statblock_revision_read",
    }
)
_CONTRACT_ARTIFACT = (
    Path(__file__).resolve().parents[2] / "openapi" / "dungeonbuddy-statblocks-v1.json"
)

_AUTH_ERROR_RESPONSES = {
    401: {"model": ErrorEnvelopeV1, "description": "Missing internal API key"},
    403: {"model": ErrorEnvelopeV1, "description": "Invalid internal API key"},
    503: {
        "model": ErrorEnvelopeV1,
        "description": "Internal service misconfigured",
    },
}

_READINESS_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    200: {"model": ReadinessResponseV1, "description": "Configuration is ready"},
    503: {"model": ReadinessResponseV1, "description": "Configuration is not ready"},
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

_composition_probe: Callable[[StatblocksV1Settings], list[str]] | None = None


def configure_composition_probe(
    probe: Callable[[StatblocksV1Settings], list[str]] | None,
) -> None:
    """Optional production probe that verifies factories/clients without secrets."""
    global _composition_probe
    _composition_probe = probe


@liveness_router.get("/statblocks/health/live", operation_id="statblocks_v1_liveness")
async def liveness() -> dict[str, str]:
    """Process-level health: no secrets or dependency probes."""
    return {"status": "live"}


def _capabilities(settings: StatblocksV1Settings | None) -> list[str]:
    if settings is None:
        return []
    capabilities = list(CAPABILITIES)
    generation_ok = settings.feature_enabled and bool(settings.openai_api_key)
    if not generation_ok:
        capabilities = [c for c in capabilities if c not in GENERATION_CAPABILITIES]
    reads_ok = settings.firestore_enabled and (
        settings.feature_enabled or settings.allow_reads_when_disabled
    )
    if not reads_ok:
        capabilities = [c for c in capabilities if c not in PERSISTENCE_CAPABILITIES]
    return capabilities


def _settings_or_none() -> StatblocksV1Settings | None:
    try:
        return StatblocksV1Settings.from_environment()
    except ConfigurationError:
        return None


def _read_routes_enabled(settings: StatblocksV1Settings) -> bool:
    return settings.firestore_enabled and (
        settings.feature_enabled or settings.allow_reads_when_disabled
    )


def evaluate_readiness(settings: StatblocksV1Settings) -> ReadinessResponseV1:
    errors = list(settings.readiness_errors())
    if not _CONTRACT_ARTIFACT.is_file():
        errors.append("contract_artifact_missing")
    if _composition_probe is not None:
        errors.extend(_composition_probe(settings))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    ordered: list[str] = []
    for error in errors:
        if error not in seen:
            seen.add(error)
            ordered.append(error)
    return ReadinessResponseV1(
        status="ready" if not ordered else "not_ready",
        contract=CONTRACT_NAME,
        generation_enabled=bool(settings.feature_enabled and settings.openai_api_key),
        read_routes_enabled=_read_routes_enabled(settings),
        errors=ordered,
    )


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


@health_router.get(
    "/statblocks/health/ready",
    response_model=ReadinessResponseV1,
    responses=_READINESS_RESPONSES,
    operation_id="statblocks_v1_readiness",
)
async def readiness() -> JSONResponse:
    """Configuration readiness, not an invasive provider availability probe."""
    try:
        settings = StatblocksV1Settings.from_environment()
    except ConfigurationError as error:
        payload = ReadinessResponseV1(
            status="not_ready",
            contract=CONTRACT_NAME,
            generation_enabled=False,
            read_routes_enabled=False,
            errors=["configuration_invalid"],
            detail=str(error),
        )
        return JSONResponse(
            status_code=503,
            content=payload.model_dump(mode="json", exclude_none=True),
        )
    payload = evaluate_readiness(settings)
    return JSONResponse(
        status_code=200 if payload.status == "ready" else 503,
        content=payload.model_dump(mode="json", exclude_none=True),
    )
