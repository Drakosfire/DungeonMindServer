"""Deterministic, thread-safe in-memory repositories for statblock v1 tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Callable

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CreateStatblockCommand,
)
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    CandidateExpiredError,
    CandidateNotFoundError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    ParentRevisionMismatchError,
    PersistenceValidationError,
    RevisionNotFoundError,
    StaleParentRevisionError,
    StatblockNotFoundError,
)
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1,
    IdempotencyOutcomeV1,
    IdempotencyRecordV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DeterministicIdFactory:
    """Monotonic test ID factory; production adapters use Firestore-safe UUIDs."""

    def __init__(self) -> None:
        self._sequence = 0

    def __call__(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}_{self._sequence:06d}"


class InMemoryCandidateRepository:
    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._candidates: dict[str, GeneratedStatblockCandidateV1] = {}

    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1:
        if candidate.candidate_id in self._candidates:
            raise ImmutableResourceConflictError("candidate", candidate.candidate_id)
        stored = _copy(candidate)
        self._candidates[candidate.candidate_id] = stored
        return _copy(stored)

    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)
        if candidate.expires_at <= (now or self._clock()):
            raise CandidateExpiredError(candidate_id)
        return _copy(candidate)


class InMemoryStatblockPersistenceRepository:
    """One lock models the atomicity expected from the Firestore implementation."""

    def __init__(
        self,
        *,
        clock: Clock = utc_now,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._clock = clock
        self._id_factory = id_factory or DeterministicIdFactory()
        self._lock = RLock()
        self._statblocks: dict[str, StatblockResourceV1] = {}
        self._revisions: dict[tuple[str, str], StatblockRevisionResourceV1] = {}
        self._idempotency: dict[tuple[str, str, str], IdempotencyRecordV1] = {}

    def get(self, statblock_id: str) -> StatblockResourceV1:
        statblock = self._statblocks.get(statblock_id)
        if statblock is None:
            raise StatblockNotFoundError(statblock_id)
        return _copy(statblock)

    def get_idempotency(
        self, caller_scope: str, operation: str, idempotency_key: str
    ) -> IdempotencyRecordV1 | None:
        record = self._idempotency.get((caller_scope, operation, idempotency_key))
        return _copy(record) if record else None

    def get_revision(self, statblock_id: str, revision_id: str) -> StatblockRevisionResourceV1:
        if statblock_id not in self._statblocks:
            raise StatblockNotFoundError(statblock_id)
        revision = self._revisions.get((statblock_id, revision_id))
        if revision is None:
            raise RevisionNotFoundError(revision_id)
        return _copy(revision)

    def list_for_statblock(self, statblock_id: str) -> list[StatblockRevisionResourceV1]:
        if statblock_id not in self._statblocks:
            raise StatblockNotFoundError(statblock_id)
        return [
            _copy(revision)
            for (owner, _), revision in self._revisions.items()
            if owner == statblock_id
        ]

    def create_statblock(
        self, command: CreateStatblockCommand
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]:
        with self._lock:
            replay = self._replay(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                command.request_digest,
            )
            if replay is not None:
                return (
                    self.get(replay.statblock_id),
                    self.get_revision(replay.statblock_id, replay.revision_id),
                )

            canonical, digest, receipt = _persistence_material(command.definition)
            now = self._clock()
            statblock_id = self._id_factory("sb")
            revision_id = self._id_factory("rev")
            if statblock_id in self._statblocks:
                raise ImmutableResourceConflictError("statblock", statblock_id)
            if (statblock_id, revision_id) in self._revisions:
                raise ImmutableRevisionConflictError(revision_id)

            definition = command.definition.model_copy(deep=True)
            asset_bindings = deepcopy(command.asset_bindings)
            provenance = deepcopy(_provenance(command.provenance, command.candidate_id))
            statblock = StatblockResourceV1(
                statblock_id=statblock_id,
                latest_revision_id=revision_id,
                created_at=now,
                created_by=command.created_by,
            )
            revision = StatblockRevisionResourceV1(
                statblock_id=statblock_id,
                revision_id=revision_id,
                definition=definition,
                canonical_definition=str(canonical),
                definition_digest=digest,
                validation_receipt=receipt,
                provenance=provenance,
                asset_bindings=asset_bindings,
                created_at=now,
            )
            self._statblocks[statblock_id] = statblock
            self._revisions[(statblock_id, revision_id)] = revision
            self._record(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                command.request_digest,
                IdempotencyOutcomeV1(statblock_id=statblock_id, revision_id=revision_id),
                now,
            )
            return _copy(statblock), _copy(revision)

    def append_revision(self, command: AppendRevisionCommand) -> StatblockRevisionResourceV1:
        with self._lock:
            replay = self._replay(
                command.caller_scope,
                "append_revision",
                command.idempotency_key,
                command.request_digest,
            )
            if replay is not None:
                return self.get_revision(replay.statblock_id, replay.revision_id)

            statblock = self._statblocks.get(command.statblock_id)
            if statblock is None:
                raise StatblockNotFoundError(command.statblock_id)
            if (command.statblock_id, command.parent_revision_id) not in self._revisions:
                raise ParentRevisionMismatchError(
                    command.statblock_id, command.parent_revision_id
                )
            if statblock.latest_revision_id != command.parent_revision_id:
                raise StaleParentRevisionError(
                    command.statblock_id,
                    command.parent_revision_id,
                    statblock.latest_revision_id,
                )

            canonical, digest, receipt = _persistence_material(command.definition)
            now = self._clock()
            revision_id = self._id_factory("rev")
            if (command.statblock_id, revision_id) in self._revisions:
                raise ImmutableRevisionConflictError(revision_id)

            definition = command.definition.model_copy(deep=True)
            asset_bindings = deepcopy(command.asset_bindings)
            provenance = deepcopy(_provenance(command.provenance, command.candidate_id))
            revision = StatblockRevisionResourceV1(
                statblock_id=command.statblock_id,
                revision_id=revision_id,
                parent_revision_id=command.parent_revision_id,
                definition=definition,
                canonical_definition=str(canonical),
                definition_digest=digest,
                validation_receipt=receipt,
                provenance=provenance,
                asset_bindings=asset_bindings,
                created_at=now,
            )
            self._revisions[(command.statblock_id, revision_id)] = revision
            self._statblocks[command.statblock_id] = statblock.model_copy(
                update={"latest_revision_id": revision_id}
            )
            self._record(
                command.caller_scope,
                "append_revision",
                command.idempotency_key,
                command.request_digest,
                IdempotencyOutcomeV1(
                    statblock_id=command.statblock_id, revision_id=revision_id
                ),
                now,
            )
            return _copy(revision)

    def _replay(
        self, scope: str, operation: str, key: str, digest: str
    ) -> IdempotencyOutcomeV1 | None:
        record = self._idempotency.get((scope, operation, key))
        if record is None:
            return None
        if record.request_digest != digest:
            raise IdempotencyConflictError(key)
        return record.outcome

    def _record(
        self,
        scope: str,
        operation: str,
        key: str,
        digest: str,
        outcome: IdempotencyOutcomeV1,
        now: datetime,
    ) -> None:
        self._idempotency[(scope, operation, key)] = IdempotencyRecordV1(
            caller_scope=scope,
            operation=operation,
            idempotency_key=key,
            request_digest=digest,
            outcome=outcome,
            created_at=now,
        )


def _persistence_material(definition: StatblockDefinitionV1):
    receipt = validate_definition(definition, ValidationMode.persistence)
    if not receipt.is_persistence_ready:
        raise PersistenceValidationError()
    canonical = canonicalize_definition(definition)
    digest = compute_definition_digest(definition)
    if receipt.definition_digest != digest:
        raise PersistenceValidationError()
    return canonical, digest, receipt


def _provenance(provenance: dict, candidate_id: str | None) -> dict:
    merged = {**provenance}
    if candidate_id:
        merged["candidate_id"] = candidate_id
    return merged


def _copy(model):
    return model.model_copy(deep=True)
