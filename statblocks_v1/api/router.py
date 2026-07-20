"""DungeonBuddy-facing internal router for statblock contract v1."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.dependencies import (
    Clock,
    Validator,
    get_candidate_repository,
    get_clock,
    get_generation_service,
    get_validator,
    require_internal_service_auth,
)
from statblocks_v1.api.http_errors import raise_for_generation_failure
from statblocks_v1.api.models import (
    ErrorEnvelopeV1,
    GenerateCandidateRequestV1,
    HealthResponseV1,
    ReviseCandidateRequestV1,
    ValidateDefinitionRequestV1,
    ValidationResponseV1,
)
from statblocks_v1.application.commands import (
    CallerProvenanceV1,
    GenerateStatblockCommandV1,
    ReviseStatblockCommandV1,
)
from statblocks_v1.application.generation import GenerationFailureV1, GenerationServiceV1
from statblocks_v1.application.repositories import CandidateRepository
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1

_AUTH_ERROR_RESPONSES = {
    401: {"model": ErrorEnvelopeV1, "description": "Missing internal API key"},
    403: {"model": ErrorEnvelopeV1, "description": "Invalid internal API key"},
    503: {
        "model": ErrorEnvelopeV1,
        "description": (
            "Internal service misconfigured, provider unavailable, or persistence unavailable"
        ),
    },
}

_CANDIDATE_ERROR_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    422: {"model": ErrorEnvelopeV1, "description": "Invalid request or generation validation failure"},
    429: {"model": ErrorEnvelopeV1, "description": "Provider rate limited"},
    500: {
        "model": ErrorEnvelopeV1,
        "description": "Unexpected generation failure (fail-closed unknown outcome)",
    },
    504: {"model": ErrorEnvelopeV1, "description": "Provider timeout"},
}

_REVISE_ERROR_RESPONSES = {
    **_CANDIDATE_ERROR_RESPONSES,
    404: {
        "model": ErrorEnvelopeV1,
        "description": "Source statblock or revision not found",
    },
}

_CANDIDATE_READ_ERROR_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    404: {"model": ErrorEnvelopeV1, "description": "Candidate not found"},
    410: {"model": ErrorEnvelopeV1, "description": "Candidate expired"},
}

_VALIDATE_ERROR_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    422: {"model": ErrorEnvelopeV1, "description": "Invalid request"},
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
    """Advertise the candidate workflow currently available to DungeonBuddy."""
    return HealthResponseV1(
        status="available",
        contract=CONTRACT_NAME,
        contract_version=CONTRACT_VERSION,
        capabilities=[
            "candidate_generate",
            "candidate_revise",
            "definition_validate",
            "candidate_read",
        ],
    )


@router.post(
    "/statblock-candidates:generate",
    response_model=GeneratedStatblockCandidateV1,
    responses=_CANDIDATE_ERROR_RESPONSES,
    operation_id="generate_statblock_candidate_v1",
)
async def generate_candidate(
    request: GenerateCandidateRequestV1,
    service: Annotated[GenerationServiceV1, Depends(get_generation_service)],
) -> GeneratedStatblockCandidateV1:
    command = GenerateStatblockCommandV1(
        request_id=request.request_id,
        ruleset=request.ruleset,
        source=request.source,
        intent=request.intent,
        context=request.context,
        asset_options=request.asset_options,
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy", actor=request.actor),
    )
    result = await asyncio.to_thread(service.generate, command)
    if isinstance(result, GenerationFailureV1):
        raise_for_generation_failure(result)
    return result


@router.post(
    "/statblock-candidates:revise",
    response_model=GeneratedStatblockCandidateV1,
    responses=_REVISE_ERROR_RESPONSES,
    operation_id="revise_statblock_candidate_v1",
)
async def revise_candidate(
    request: ReviseCandidateRequestV1,
    service: Annotated[GenerationServiceV1, Depends(get_generation_service)],
) -> GeneratedStatblockCandidateV1:
    command = ReviseStatblockCommandV1(
        request_id=request.request_id,
        ruleset=request.ruleset,
        revision_instructions=request.revision_instructions,
        source_definition=request.source_definition,
        source_locator=request.source_locator,
        source=request.source,
        intent=request.intent,
        context=request.context,
        asset_options=request.asset_options,
        preserve_element_keys=request.preserve_element_keys,
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy", actor=request.actor),
    )
    result = await asyncio.to_thread(service.revise, command)
    if isinstance(result, GenerationFailureV1):
        raise_for_generation_failure(result)
    return result


@router.post(
    "/statblock-definitions:validate",
    response_model=ValidationResponseV1,
    responses=_VALIDATE_ERROR_RESPONSES,
    operation_id="validate_statblock_definition_v1",
)
async def validate_definition_route(
    request: ValidateDefinitionRequestV1,
    validator: Annotated[Validator, Depends(get_validator)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ValidationResponseV1:
    receipt = await asyncio.to_thread(
        validator, request.definition, ValidationMode.editor_preview, clock()
    )
    return ValidationResponseV1(
        validation_receipt=receipt,
        definition_digest=receipt.definition_digest,
    )


@router.get(
    "/statblock-candidates/{candidate_id}",
    response_model=GeneratedStatblockCandidateV1,
    responses=_CANDIDATE_READ_ERROR_RESPONSES,
    operation_id="get_statblock_candidate_v1",
)
async def get_candidate(
    candidate_id: str,
    candidates: Annotated[CandidateRepository, Depends(get_candidate_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> GeneratedStatblockCandidateV1:
    return await asyncio.to_thread(candidates.get, candidate_id, now=clock())
