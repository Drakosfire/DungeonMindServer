"""DungeonBuddy-facing internal router for statblock contract v1."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from statblocks_v1.api.dependencies import (
    Clock,
    Validator,
    get_candidate_repository,
    get_clock,
    get_generation_service,
    get_persistence_repository,
    get_revision_service,
    get_validator,
    require_generation_enabled,
    require_internal_service_auth,
)
from statblocks_v1.api.http_errors import raise_for_generation_failure
from statblocks_v1.api.models import (
    AppendRevisionRequestV1,
    CreateStatblockRequestV1,
    CreateStatblockResponseV1,
    ErrorEnvelopeV1,
    GenerateCandidateRequestV1,
    RevisionListResponseV1,
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
from statblocks_v1.application.repositories import (
    CandidateRepository,
    StatblockPersistenceRepository,
)
from statblocks_v1.application.revisions import RevisionServiceV1
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)

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

_RESOURCE_WRITE_ERROR_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    404: {
        "model": ErrorEnvelopeV1,
        "description": "Statblock, revision, or acceptance candidate not found",
    },
    409: {
        "model": ErrorEnvelopeV1,
        "description": (
            "Idempotency conflict, parent mismatch, stale parent, or immutable ID conflict"
        ),
    },
    422: {
        "model": ErrorEnvelopeV1,
        "description": "Request validation or persistence-mode validation failed",
    },
}

_RESOURCE_READ_ERROR_RESPONSES = {
    **_AUTH_ERROR_RESPONSES,
    404: {"model": ErrorEnvelopeV1, "description": "Statblock or revision not found"},
}

router = APIRouter(
    prefix="/api/internal/dungeonbuddy/v1",
    tags=["DungeonBuddy Statblocks v1"],
    dependencies=[Depends(require_internal_service_auth)],
    responses=_AUTH_ERROR_RESPONSES,
)


@router.post(
    "/statblock-candidates:generate",
    response_model=GeneratedStatblockCandidateV1,
    responses=_CANDIDATE_ERROR_RESPONSES,
    operation_id="generate_statblock_candidate_v1",
    dependencies=[Depends(require_generation_enabled)],
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
    dependencies=[Depends(require_generation_enabled)],
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


@router.post(
    "/statblocks",
    response_model=CreateStatblockResponseV1,
    responses=_RESOURCE_WRITE_ERROR_RESPONSES,
    operation_id="create_statblock_v1",
)
async def create_statblock(
    request: CreateStatblockRequestV1,
    service: Annotated[RevisionServiceV1, Depends(get_revision_service)],
) -> CreateStatblockResponseV1:
    statblock, revision = await asyncio.to_thread(
        service.create,
        idempotency_key=request.idempotency_key,
        definition=request.definition,
        change_summary=request.change_summary,
        accepted_through=request.accepted_through,
        actor=request.actor,
        asset_bindings=request.asset_bindings,
        candidate_id=request.candidate_id,
    )
    return CreateStatblockResponseV1(statblock=statblock, revision=revision)


@router.post(
    "/statblocks/{statblock_id}/revisions",
    response_model=StatblockRevisionResourceV1,
    responses=_RESOURCE_WRITE_ERROR_RESPONSES,
    operation_id="append_statblock_revision_v1",
)
async def append_revision(
    statblock_id: str,
    request: AppendRevisionRequestV1,
    service: Annotated[RevisionServiceV1, Depends(get_revision_service)],
) -> StatblockRevisionResourceV1:
    return await asyncio.to_thread(
        service.append,
        statblock_id=statblock_id,
        parent_revision_id=request.parent_revision_id,
        idempotency_key=request.idempotency_key,
        definition=request.definition,
        change_summary=request.change_summary,
        accepted_through=request.accepted_through,
        actor=request.actor,
        asset_bindings=request.asset_bindings,
        candidate_id=request.candidate_id,
    )


@router.get(
    "/statblocks/{statblock_id}",
    response_model=StatblockResourceV1,
    responses=_RESOURCE_READ_ERROR_RESPONSES,
    operation_id="get_statblock_v1",
)
async def get_statblock(
    statblock_id: str,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> StatblockResourceV1:
    return await asyncio.to_thread(persistence.get, statblock_id)


@router.get(
    "/statblocks/{statblock_id}/revisions",
    response_model=RevisionListResponseV1,
    responses=_RESOURCE_READ_ERROR_RESPONSES,
    operation_id="list_statblock_revisions_v1",
)
async def list_revisions(
    statblock_id: str,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> RevisionListResponseV1:
    revisions = await asyncio.to_thread(persistence.list_for_statblock, statblock_id)
    return RevisionListResponseV1(
        revisions=sorted(
            revisions, key=lambda revision: (revision.created_at, revision.revision_id)
        )
    )


@router.get(
    "/statblocks/{statblock_id}/revisions/{revision_id}",
    response_model=StatblockRevisionResourceV1,
    responses=_RESOURCE_READ_ERROR_RESPONSES,
    operation_id="get_statblock_revision_v1",
)
async def get_revision(
    statblock_id: str,
    revision_id: str,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> StatblockRevisionResourceV1:
    """Resolve exactly the locator supplied by the caller; never select latest."""
    return await asyncio.to_thread(persistence.get_revision, statblock_id, revision_id)
