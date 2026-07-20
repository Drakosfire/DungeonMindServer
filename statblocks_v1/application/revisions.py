"""Application service for immutable logical-statblock revisions."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CandidateRepository,
    CreateStatblockCommand,
    StatblockPersistenceRepository,
)
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import IdempotencyConflictError, PersistenceValidationError
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

# Service-authenticated caller identity. End-user ``actor`` is provenance only.
SERVICE_CREATED_BY = "dungeonbuddy"


class RevisionServiceV1:
    """Validate and enrich acceptances before the atomic persistence boundary.

    Idempotency is consulted before candidate lookup so same-key replay remains
    available after Firestore TTL deletes the source candidate document.
    """

    def __init__(
        self,
        *,
        persistence: StatblockPersistenceRepository,
        candidates: CandidateRepository,
        clock: Callable[[], datetime],
    ) -> None:
        self._persistence = persistence
        self._candidates = candidates
        self._clock = clock

    def create(
        self,
        *,
        idempotency_key: str,
        definition: StatblockDefinitionV1,
        change_summary: str,
        accepted_through: dict[str, Any] | None = None,
        actor: str | None = None,
        asset_bindings: list[dict[str, Any]] | None = None,
        candidate_id: str | None = None,
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]:
        self._validate_persistence(definition)
        client_provenance = _seal_client_provenance(
            change_summary=change_summary,
            accepted_through=accepted_through,
            actor=actor,
        )
        probe = CreateStatblockCommand(
            caller_scope="dungeonbuddy",
            idempotency_key=idempotency_key,
            definition=definition,
            created_by=SERVICE_CREATED_BY,
            provenance=client_provenance,
            asset_bindings=asset_bindings,
            candidate_id=candidate_id,
        )
        replayed = self._replay_create(probe)
        if replayed is not None:
            return replayed

        enriched = self._with_candidate_audit(candidate_id, definition, client_provenance)
        return self._persistence.create_statblock(
            CreateStatblockCommand(
                caller_scope="dungeonbuddy",
                idempotency_key=idempotency_key,
                definition=definition,
                created_by=SERVICE_CREATED_BY,
                provenance=enriched,
                asset_bindings=asset_bindings,
                candidate_id=candidate_id,
            )
        )

    def append(
        self,
        *,
        statblock_id: str,
        parent_revision_id: str,
        idempotency_key: str,
        definition: StatblockDefinitionV1,
        change_summary: str,
        accepted_through: dict[str, Any] | None = None,
        actor: str | None = None,
        asset_bindings: list[dict[str, Any]] | None = None,
        candidate_id: str | None = None,
    ) -> StatblockRevisionResourceV1:
        self._validate_persistence(definition)
        client_provenance = _seal_client_provenance(
            change_summary=change_summary,
            accepted_through=accepted_through,
            actor=actor,
        )
        probe = AppendRevisionCommand(
            caller_scope="dungeonbuddy",
            idempotency_key=idempotency_key,
            statblock_id=statblock_id,
            parent_revision_id=parent_revision_id,
            definition=definition,
            provenance=client_provenance,
            asset_bindings=asset_bindings,
            candidate_id=candidate_id,
        )
        replayed = self._replay_append(probe)
        if replayed is not None:
            return replayed

        enriched = self._with_candidate_audit(candidate_id, definition, client_provenance)
        return self._persistence.append_revision(
            AppendRevisionCommand(
                caller_scope="dungeonbuddy",
                idempotency_key=idempotency_key,
                statblock_id=statblock_id,
                parent_revision_id=parent_revision_id,
                definition=definition,
                provenance=enriched,
                asset_bindings=asset_bindings,
                candidate_id=candidate_id,
            )
        )

    def _validate_persistence(self, definition: StatblockDefinitionV1) -> None:
        receipt = validate_definition(
            definition, ValidationMode.persistence, validated_at=self._clock()
        )
        if not receipt.is_persistence_ready:
            raise PersistenceValidationError(receipt)

    def _replay_create(
        self, command: CreateStatblockCommand
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1] | None:
        record = self._persistence.get_idempotency(
            command.caller_scope, "create_statblock", command.idempotency_key
        )
        if record is None:
            return None
        if record.request_digest != command.request_digest:
            raise IdempotencyConflictError(command.idempotency_key)
        return (
            self._persistence.get(record.outcome.statblock_id),
            self._persistence.get_revision(
                record.outcome.statblock_id, record.outcome.revision_id
            ),
        )

    def _replay_append(self, command: AppendRevisionCommand) -> StatblockRevisionResourceV1 | None:
        record = self._persistence.get_idempotency(
            command.caller_scope, "append_revision", command.idempotency_key
        )
        if record is None:
            return None
        if record.request_digest != command.request_digest:
            raise IdempotencyConflictError(command.idempotency_key)
        return self._persistence.get_revision(
            record.outcome.statblock_id, record.outcome.revision_id
        )

    def _with_candidate_audit(
        self,
        candidate_id: str | None,
        accepted_definition: StatblockDefinitionV1,
        provenance: dict[str, Any],
    ) -> dict[str, Any]:
        result = deepcopy(provenance)
        if candidate_id is None:
            return result
        candidate = self._candidates.get_for_acceptance(candidate_id)
        candidate_digest = candidate.validation_receipt.definition_digest
        accepted_digest = compute_definition_digest(accepted_definition)
        result["candidate"] = _candidate_audit(candidate, candidate_digest, accepted_digest)
        return result


def _seal_client_provenance(
    *,
    change_summary: str,
    accepted_through: dict[str, Any] | None,
    actor: str | None,
) -> dict[str, Any]:
    """Build caller provenance from typed fields only (no free-form spoof surface)."""

    sealed: dict[str, Any] = {
        "change_summary": change_summary,
        "accepted_through": deepcopy(accepted_through or {}),
    }
    if actor:
        sealed["accepted_by"] = actor
    return sealed


def _candidate_audit(
    candidate: GeneratedStatblockCandidateV1,
    source_digest: str,
    accepted_digest: str,
) -> dict[str, Any]:
    """Keep audit evidence even after candidate read expiry."""

    return {
        "candidate_id": candidate.candidate_id,
        "source_definition_digest": source_digest,
        "generation_receipt": (
            candidate.generation_receipt.model_dump(mode="json")
            if candidate.generation_receipt
            else None
        ),
        "accepted_definition_changed": source_digest != accepted_digest,
    }
