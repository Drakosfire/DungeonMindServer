"""Deterministic, thread-safe in-memory repositories for statblock v1 tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Callable

from datetime import timedelta

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CreateStatblockCommand,
    GenerateBeginClaimed,
    GenerateBeginCompleted,
    GenerateBeginFailed,
    GenerateBeginInProgress,
    GenerateBeginResult,
    GenerateCompleteResult,
    candidate_belongs_to_generate_operation,
    verify_generate_operation_lookup_identity,
)
from statblocks_v1.domain.candidate_operations import (
    GENERATE_CANDIDATE_OPERATION,
    CandidateGenerationFailureSnapshotV1,
    CandidateGenerationOperationV1,
    CandidateGenerationStatusV1,
)
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    CandidateExpiredError,
    CandidateNotFoundError,
    GenerateOperationIntegrityError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    ParentRevisionMismatchError,
    PersistenceUnavailableError,
    PersistenceValidationError,
    RevisionNotFoundError,
    StaleParentRevisionError,
    StatblockNotFoundError,
)
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    STATBLOCK_CONTRACT,
    STATBLOCK_CONTRACT_VERSION,
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
        self._lock = RLock()
        self._candidates: dict[str, GeneratedStatblockCandidateV1] = {}

    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1:
        with self._lock:
            if candidate.candidate_id in self._candidates:
                raise ImmutableResourceConflictError("candidate", candidate.candidate_id)
            stored = _copy(candidate)
            self._candidates[candidate.candidate_id] = stored
            return _copy(stored)

    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1:
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise CandidateNotFoundError(candidate_id)
            if candidate.expires_at <= (now or self._clock()):
                raise CandidateExpiredError(candidate_id)
            return _copy(candidate)

    def get_for_acceptance(self, candidate_id: str) -> GeneratedStatblockCandidateV1:
        """Expiry blocks candidate workflow reads, never durable audit acceptance."""
        with self._lock:
            candidate = self._candidates.get(candidate_id)
            if candidate is None:
                raise CandidateNotFoundError(candidate_id)
            return _copy(candidate)

    def _create_unlocked(
        self, candidate: GeneratedStatblockCandidateV1
    ) -> GeneratedStatblockCandidateV1:
        if candidate.candidate_id in self._candidates:
            raise ImmutableResourceConflictError("candidate", candidate.candidate_id)
        stored = _copy(candidate)
        self._candidates[candidate.candidate_id] = stored
        return _copy(stored)

    def _get_unlocked(
        self,
        candidate_id: str,
        *,
        now: datetime | None = None,
        enforce_expiry: bool = True,
    ) -> GeneratedStatblockCandidateV1:
        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(candidate_id)
        if enforce_expiry and candidate.expires_at <= (now or self._clock()):
            raise CandidateExpiredError(candidate_id)
        return _copy(candidate)


class InMemoryCandidateGenerationOperationRepository:
    """In-memory generate-operation state machine sharing the candidate lock."""

    def __init__(
        self,
        candidates: InMemoryCandidateRepository,
        *,
        clock: Clock | None = None,
    ) -> None:
        self._candidates = candidates
        self._clock = clock or candidates._clock
        self._lock = candidates._lock
        self._operations: dict[tuple[str, str], CandidateGenerationOperationV1] = {}

    def get_generate_operation(
        self, caller_scope: str, request_id: str
    ) -> CandidateGenerationOperationV1 | None:
        with self._lock:
            record = self._operations.get((caller_scope, request_id))
            if record is None:
                return None
            return _copy(
                verify_generate_operation_lookup_identity(
                    record, caller_scope=caller_scope, request_id=request_id
                )
            )

    def begin_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        candidate_id_factory: Callable[[], str],
        lease_owner: str,
        lease_duration_seconds: int,
    ) -> GenerateBeginResult:
        with self._lock:
            now = self._clock()
            key = (caller_scope, request_id)
            existing = self._operations.get(key)
            if existing is None:
                operation = CandidateGenerationOperationV1(
                    caller_scope=caller_scope,
                    operation=GENERATE_CANDIDATE_OPERATION,
                    request_id=request_id,
                    request_digest=request_digest,
                    candidate_id=candidate_id_factory(),
                    status=CandidateGenerationStatusV1.pending,
                    lease_owner=lease_owner,
                    lease_expires_at=now + timedelta(seconds=lease_duration_seconds),
                    attempt_count=1,
                    created_at=now,
                    updated_at=now,
                )
                self._operations[key] = operation
                return GenerateBeginClaimed(operation=_copy(operation))

            existing = verify_generate_operation_lookup_identity(
                existing, caller_scope=caller_scope, request_id=request_id
            )
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)

            if existing.status is CandidateGenerationStatusV1.completed:
                return GenerateBeginCompleted(operation=_copy(existing))
            if existing.status is CandidateGenerationStatusV1.failed:
                if existing.failure is None:
                    raise PersistenceUnavailableError()
                return GenerateBeginFailed(failure=_copy(existing.failure))

            if existing.lease_expires_at > now:
                return GenerateBeginInProgress(
                    candidate_id=existing.candidate_id,
                    lease_expires_at=existing.lease_expires_at,
                )

            claimed = existing.model_copy(
                update={
                    "lease_owner": lease_owner,
                    "lease_expires_at": now + timedelta(seconds=lease_duration_seconds),
                    "attempt_count": existing.attempt_count + 1,
                    "updated_at": now,
                }
            )
            self._operations[key] = claimed
            return GenerateBeginClaimed(operation=_copy(claimed))

    def complete_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        candidate: GeneratedStatblockCandidateV1,
    ) -> GenerateCompleteResult:
        with self._lock:
            now = self._clock()
            key = (caller_scope, request_id)
            existing = self._operations.get(key)
            if existing is None:
                raise PersistenceUnavailableError()
            existing = verify_generate_operation_lookup_identity(
                existing, caller_scope=caller_scope, request_id=request_id
            )
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)
            if candidate.candidate_id != existing.candidate_id:
                raise ImmutableResourceConflictError("candidate", candidate.candidate_id)

            if existing.status is CandidateGenerationStatusV1.failed:
                if existing.failure is None:
                    raise PersistenceUnavailableError()
                # Terminal failure is immutable; do not create under this request key.
                raise ImmutableResourceConflictError("candidate", existing.candidate_id)

            if existing.status is CandidateGenerationStatusV1.completed:
                stored = self._candidates._get_unlocked(
                    existing.candidate_id, now=now, enforce_expiry=False
                )
                if not candidate_belongs_to_generate_operation(stored, existing):
                    raise GenerateOperationIntegrityError(
                        request_id,
                        candidate_id=existing.candidate_id,
                        reason=(
                            "Completed generate points to a candidate that does not "
                            "belong to this operation"
                        ),
                    )
                return GenerateCompleteResult(candidate=stored, already_completed=True)

            try:
                stored = self._candidates._create_unlocked(candidate)
            except ImmutableResourceConflictError:
                stored = self._candidates._get_unlocked(
                    existing.candidate_id, now=now, enforce_expiry=False
                )
                if not candidate_belongs_to_generate_operation(stored, existing):
                    raise ImmutableResourceConflictError(
                        "candidate", existing.candidate_id
                    )

            self._operations[key] = existing.model_copy(
                update={
                    "status": CandidateGenerationStatusV1.completed,
                    "updated_at": now,
                    "completed_at": now,
                    "failure": None,
                    "candidate_expires_at": stored.expires_at,
                }
            )
            return GenerateCompleteResult(candidate=stored, already_completed=False)

    def fail_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        failure: CandidateGenerationFailureSnapshotV1,
    ) -> CandidateGenerationFailureSnapshotV1:
        with self._lock:
            now = self._clock()
            key = (caller_scope, request_id)
            existing = self._operations.get(key)
            if existing is None:
                raise PersistenceUnavailableError()
            existing = verify_generate_operation_lookup_identity(
                existing, caller_scope=caller_scope, request_id=request_id
            )
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)

            if existing.status is CandidateGenerationStatusV1.completed:
                raise ImmutableResourceConflictError("candidate", existing.candidate_id)
            if existing.status is CandidateGenerationStatusV1.failed:
                if existing.failure is None:
                    raise PersistenceUnavailableError()
                return _copy(existing.failure)

            if existing.lease_owner != lease_owner:
                # Lease taken over; never echo an uncommitted local failure.
                raise ImmutableResourceConflictError("candidate", existing.candidate_id)

            snapshot = _copy(failure)
            self._operations[key] = existing.model_copy(
                update={
                    "status": CandidateGenerationStatusV1.failed,
                    "failure": snapshot,
                    "updated_at": now,
                    "completed_at": now,
                }
            )
            return snapshot


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
        with self._lock:
            statblock = self._statblocks.get(statblock_id)
            if statblock is None:
                raise StatblockNotFoundError(statblock_id)
            return _copy(statblock)

    def get_idempotency(
        self, caller_scope: str, operation: str, idempotency_key: str
    ) -> IdempotencyRecordV1 | None:
        with self._lock:
            record = self._idempotency.get((caller_scope, operation, idempotency_key))
            return _copy(record) if record else None

    def get_revision(self, statblock_id: str, revision_id: str) -> StatblockRevisionResourceV1:
        with self._lock:
            if statblock_id not in self._statblocks:
                raise StatblockNotFoundError(statblock_id)
            revision = self._revisions.get((statblock_id, revision_id))
            if revision is None:
                raise RevisionNotFoundError(revision_id)
            return _copy(revision)

    def list_for_statblock(self, statblock_id: str) -> list[StatblockRevisionResourceV1]:
        with self._lock:
            if statblock_id not in self._statblocks:
                raise StatblockNotFoundError(statblock_id)
            return [
                _copy(revision)
                for (owner, _), revision in tuple(self._revisions.items())
                if owner == statblock_id
            ]

    def create_statblock(
        self, command: CreateStatblockCommand
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]:
        # Snapshot once at the repository boundary; command fields are already frozen.
        request_digest = command.request_digest
        definition = command.definition
        provenance = command.provenance
        asset_bindings = command.asset_bindings
        with self._lock:
            replay = self._replay(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                request_digest,
            )
            if replay is not None:
                return (
                    self.get(replay.statblock_id),
                    self.get_revision(replay.statblock_id, replay.revision_id),
                )

            canonical, digest, receipt = _persistence_material(definition)
            now = self._clock()
            statblock_id = self._id_factory("sb")
            revision_id = self._id_factory("rev")
            if statblock_id in self._statblocks:
                raise ImmutableResourceConflictError("statblock", statblock_id)
            if (statblock_id, revision_id) in self._revisions:
                raise ImmutableRevisionConflictError(revision_id)

            stored_definition = definition.model_copy(deep=True)
            stored_bindings = deepcopy(asset_bindings)
            stored_provenance = deepcopy(_provenance(provenance, command.candidate_id))
            statblock = StatblockResourceV1(
                statblock_id=statblock_id,
                latest_revision_id=revision_id,
                created_at=now,
                created_by=command.created_by,
            )
            revision = StatblockRevisionResourceV1(
                statblock_id=statblock_id,
                revision_id=revision_id,
                contract=STATBLOCK_CONTRACT,
                contract_version=STATBLOCK_CONTRACT_VERSION,
                definition=stored_definition,
                canonical_definition=str(canonical),
                definition_digest=digest,
                validation_receipt=receipt,
                provenance=stored_provenance,
                asset_bindings=stored_bindings,
                created_at=now,
            )
            self._statblocks[statblock_id] = statblock
            self._revisions[(statblock_id, revision_id)] = revision
            self._record(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                request_digest,
                IdempotencyOutcomeV1(statblock_id=statblock_id, revision_id=revision_id),
                now,
            )
            return _copy(statblock), _copy(revision)

    def append_revision(self, command: AppendRevisionCommand) -> StatblockRevisionResourceV1:
        request_digest = command.request_digest
        definition = command.definition
        provenance = command.provenance
        asset_bindings = command.asset_bindings
        with self._lock:
            replay = self._replay(
                command.caller_scope,
                "append_revision",
                command.idempotency_key,
                request_digest,
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

            canonical, digest, receipt = _persistence_material(definition)
            now = self._clock()
            revision_id = self._id_factory("rev")
            if (command.statblock_id, revision_id) in self._revisions:
                raise ImmutableRevisionConflictError(revision_id)

            stored_definition = definition.model_copy(deep=True)
            stored_bindings = deepcopy(asset_bindings)
            stored_provenance = deepcopy(_provenance(provenance, command.candidate_id))
            revision = StatblockRevisionResourceV1(
                statblock_id=command.statblock_id,
                revision_id=revision_id,
                parent_revision_id=command.parent_revision_id,
                contract=STATBLOCK_CONTRACT,
                contract_version=STATBLOCK_CONTRACT_VERSION,
                definition=stored_definition,
                canonical_definition=str(canonical),
                definition_digest=digest,
                validation_receipt=receipt,
                provenance=stored_provenance,
                asset_bindings=stored_bindings,
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
                request_digest,
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
        raise PersistenceValidationError(receipt)
    canonical = canonicalize_definition(definition)
    digest = compute_definition_digest(definition)
    if receipt.definition_digest != digest:
        raise PersistenceValidationError(receipt)
    return canonical, digest, receipt


def _provenance(provenance: dict, candidate_id: str | None) -> dict:
    merged = {**provenance}
    if candidate_id:
        merged["candidate_id"] = candidate_id
    return merged


def _copy(model):
    return model.model_copy(deep=True)
