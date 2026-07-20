"""DungeonBuddy-facing internal router for statblock contract v1."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request

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
    require_persistence_enabled,
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
from statblocks_v1.observability import bind_outcome, log_operation

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


def _issue_counts(receipt: object) -> dict[str, int]:
    issues = getattr(receipt, "issues", None) or []
    counts = {"errors": 0, "warnings": 0, "info": 0}
    for issue in issues:
        severity = getattr(issue, "severity", None) or (
            issue.get("severity") if isinstance(issue, dict) else None
        )
        key = getattr(severity, "value", None) or str(severity or "info")
        key = str(key).lower()
        if key in counts:
            counts[key] += 1
        else:
            counts["info"] += 1
    return counts


def _bind_candidate(http_request: Request, candidate: GeneratedStatblockCandidateV1) -> None:
    receipt = candidate.generation_receipt
    bind_outcome(
        http_request,
        "success",
        operation="candidate_generate",
        candidate_id=candidate.candidate_id,
        caller_scope="dungeonbuddy",
        validation_errors=_issue_counts(candidate.validation_receipt)["errors"],
        validation_warnings=_issue_counts(candidate.validation_receipt)["warnings"],
        provider=receipt.provider if receipt else None,
        model=receipt.model if receipt else None,
        schema_fingerprint=receipt.schema_fingerprint if receipt else None,
        provider_latency_ms=receipt.latency_ms if receipt else None,
        input_tokens=receipt.input_tokens if receipt else None,
        output_tokens=receipt.output_tokens if receipt else None,
    )
    log_operation(
        "candidate_persisted",
        candidate_id=candidate.candidate_id,
        definition_digest=candidate.validation_receipt.definition_digest,
        asset_count=len(candidate.assets),
        asset_warning_count=len(candidate.asset_warnings),
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
    http_request: Request,
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
        bind_outcome(http_request, result.kind, operation="candidate_generate")
        raise_for_generation_failure(result)
    _bind_candidate(http_request, result)
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
    http_request: Request,
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
        bind_outcome(http_request, result.kind, operation="candidate_revise")
        raise_for_generation_failure(result)
    _bind_candidate(http_request, result)
    return result


@router.post(
    "/statblock-definitions:validate",
    response_model=ValidationResponseV1,
    responses=_VALIDATE_ERROR_RESPONSES,
    operation_id="validate_statblock_definition_v1",
)
async def validate_definition_route(
    request: ValidateDefinitionRequestV1,
    http_request: Request,
    validator: Annotated[Validator, Depends(get_validator)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ValidationResponseV1:
    receipt = await asyncio.to_thread(
        validator, request.definition, ValidationMode.editor_preview, clock()
    )
    counts = _issue_counts(receipt)
    bind_outcome(
        http_request,
        "success",
        operation="definition_validate",
        validation_errors=counts["errors"],
        validation_warnings=counts["warnings"],
        definition_digest=receipt.definition_digest,
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
    dependencies=[Depends(require_persistence_enabled)],
)
async def get_candidate(
    candidate_id: str,
    http_request: Request,
    candidates: Annotated[CandidateRepository, Depends(get_candidate_repository)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> GeneratedStatblockCandidateV1:
    candidate = await asyncio.to_thread(candidates.get, candidate_id, now=clock())
    bind_outcome(
        http_request,
        "success",
        operation="candidate_read",
        candidate_id=candidate.candidate_id,
    )
    return candidate


@router.post(
    "/statblocks",
    response_model=CreateStatblockResponseV1,
    responses=_RESOURCE_WRITE_ERROR_RESPONSES,
    operation_id="create_statblock_v1",
    dependencies=[Depends(require_persistence_enabled)],
)
async def create_statblock(
    request: CreateStatblockRequestV1,
    http_request: Request,
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
    bind_outcome(
        http_request,
        "success",
        operation="statblock_create",
        statblock_id=statblock.statblock_id,
        revision_id=revision.revision_id,
        definition_digest=revision.definition_digest,
        idempotency_key_present=True,
    )
    log_operation(
        "statblock_created",
        statblock_id=statblock.statblock_id,
        revision_id=revision.revision_id,
        definition_digest=revision.definition_digest,
    )
    return CreateStatblockResponseV1(statblock=statblock, revision=revision)


@router.post(
    "/statblocks/{statblock_id}/revisions",
    response_model=StatblockRevisionResourceV1,
    responses=_RESOURCE_WRITE_ERROR_RESPONSES,
    operation_id="append_statblock_revision_v1",
    dependencies=[Depends(require_persistence_enabled)],
)
async def append_revision(
    statblock_id: str,
    request: AppendRevisionRequestV1,
    http_request: Request,
    service: Annotated[RevisionServiceV1, Depends(get_revision_service)],
) -> StatblockRevisionResourceV1:
    revision = await asyncio.to_thread(
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
    bind_outcome(
        http_request,
        "success",
        operation="statblock_revision_append",
        statblock_id=revision.statblock_id,
        revision_id=revision.revision_id,
        parent_revision_id=revision.parent_revision_id,
        definition_digest=revision.definition_digest,
        idempotency_key_present=True,
    )
    return revision


@router.get(
    "/statblocks/{statblock_id}",
    response_model=StatblockResourceV1,
    responses=_RESOURCE_READ_ERROR_RESPONSES,
    operation_id="get_statblock_v1",
    dependencies=[Depends(require_persistence_enabled)],
)
async def get_statblock(
    statblock_id: str,
    http_request: Request,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> StatblockResourceV1:
    resource = await asyncio.to_thread(persistence.get, statblock_id)
    bind_outcome(
        http_request,
        "success",
        operation="statblock_read",
        statblock_id=resource.statblock_id,
        revision_id=resource.latest_revision_id,
    )
    return resource


@router.get(
    "/statblocks/{statblock_id}/revisions",
    response_model=RevisionListResponseV1,
    responses=_RESOURCE_READ_ERROR_RESPONSES,
    operation_id="list_statblock_revisions_v1",
    dependencies=[Depends(require_persistence_enabled)],
)
async def list_revisions(
    statblock_id: str,
    http_request: Request,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> RevisionListResponseV1:
    revisions = await asyncio.to_thread(persistence.list_for_statblock, statblock_id)
    bind_outcome(
        http_request,
        "success",
        operation="statblock_revision_list",
        statblock_id=statblock_id,
        revision_count=len(revisions),
    )
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
    dependencies=[Depends(require_persistence_enabled)],
)
async def get_revision(
    statblock_id: str,
    revision_id: str,
    http_request: Request,
    persistence: Annotated[
        StatblockPersistenceRepository, Depends(get_persistence_repository)
    ],
) -> StatblockRevisionResourceV1:
    """Resolve exactly the locator supplied by the caller; never select latest."""
    revision = await asyncio.to_thread(persistence.get_revision, statblock_id, revision_id)
    bind_outcome(
        http_request,
        "success",
        operation="statblock_revision_read",
        statblock_id=revision.statblock_id,
        revision_id=revision.revision_id,
        definition_digest=revision.definition_digest,
    )
    return revision
