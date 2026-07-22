"""Synchronous Firestore adapters for immutable statblock v1 persistence.

Callers in async code must use ``await asyncio.to_thread(repository.method, ...)``.
The adapter deliberately does not expose async-looking methods that could block
the event loop.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from pydantic import AnyUrl

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CreateStatblockCommand,
    GenerateBeginClaimed,
    GenerateBeginCompleted,
    GenerateBeginFailed,
    GenerateBeginInProgress,
    GenerateBeginResult,
)
from statblocks_v1.domain.candidate_operations import (
    GENERATE_CANDIDATE_OPERATION,
    CandidateGenerationFailureSnapshotV1,
    CandidateGenerationOperationV1,
    CandidateGenerationStatusV1,
)
from statblocks_v1.domain.errors import (
    CandidateExpiredError,
    CandidateNotFoundError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    ParentRevisionMismatchError,
    PersistenceUnavailableError,
    RevisionNotFoundError,
    StaleParentRevisionError,
    StatblockNotFoundError,
    TransactionIndeterminateError,
)
from statblocks_v1.domain.resources import (
    STATBLOCK_CONTRACT,
    STATBLOCK_CONTRACT_VERSION,
    GeneratedStatblockCandidateV1,
    IdempotencyOutcomeV1,
    IdempotencyRecordV1,
    StatblockResourceV1,
    StatblockRevisionResourceV1,
)
from statblocks_v1.infrastructure.memory_repositories import (
    _persistence_material,
    _provenance,
    utc_now,
)

CANDIDATES_COLLECTION = "dungeonbuddy_statblock_candidates_v1"
STATBLOCKS_COLLECTION = "dungeonbuddy_statblocks_v1"
IDEMPOTENCY_COLLECTION = "dungeonbuddy_statblock_idempotency_v1"
GENERATE_OPS_COLLECTION = "dungeonbuddy_statblock_candidate_generate_ops_v1"


class FirestoreCandidateRepository:
    """Candidate documents are mutable only for Firestore TTL deletion."""

    def __init__(
        self,
        client: Any,
        *,
        clock: Callable[[], datetime] = utc_now,
        candidates_collection: str = CANDIDATES_COLLECTION,
        idempotency_collection: str = IDEMPOTENCY_COLLECTION,
    ) -> None:
        self._client, self._clock = client, clock
        self._candidates_collection = candidates_collection
        self._idempotency_collection = idempotency_collection

    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1:
        stored = candidate.model_copy(deep=True)
        try:
            self._client.collection(self._candidates_collection).document(stored.candidate_id).create(
                _dump(stored)
            )
        except Exception as error:
            if _is_already_exists(error):
                raise ImmutableResourceConflictError("candidate", stored.candidate_id) from error
            raise PersistenceUnavailableError() from error
        return stored.model_copy(deep=True)

    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1:
        try:
            snapshot = self._client.collection(self._candidates_collection).document(candidate_id).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = GeneratedStatblockCandidateV1.model_validate(snapshot.to_dict())
        if candidate.expires_at <= (now or self._clock()):
            raise CandidateExpiredError(candidate_id)
        return candidate

    def get_for_acceptance(self, candidate_id: str) -> GeneratedStatblockCandidateV1:
        """Read retained candidate audit data without applying workflow expiry."""
        try:
            snapshot = self._client.collection(self._candidates_collection).document(candidate_id).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        return GeneratedStatblockCandidateV1.model_validate(snapshot.to_dict())


class FirestoreCandidateGenerationOperationRepository:
    """Transactional generate-operation adapter with atomic candidate completion."""

    def __init__(
        self,
        client: Any,
        *,
        clock: Callable[[], datetime] = utc_now,
        candidates_collection: str = CANDIDATES_COLLECTION,
        generate_ops_collection: str = GENERATE_OPS_COLLECTION,
    ) -> None:
        self._client = client
        self._clock = clock
        self._candidates_collection = candidates_collection
        self._generate_ops_collection = generate_ops_collection

    def get_generate_operation(
        self, caller_scope: str, request_id: str
    ) -> CandidateGenerationOperationV1 | None:
        try:
            snapshot = self._operation_document(caller_scope, request_id).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            return None
        return CandidateGenerationOperationV1.model_validate(snapshot.to_dict())

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
        from google.cloud.firestore_v1 import transactional

        op_ref = self._operation_document(caller_scope, request_id)
        result_box: dict[str, GenerateBeginResult] = {}

        @transactional
        def operation_fn(transaction):
            now = self._clock()
            existing_snap = op_ref.get(transaction=transaction)
            if not existing_snap.exists:
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
                transaction.create(op_ref, _dump(operation))
                result_box["result"] = GenerateBeginClaimed(operation=operation)
                return

            existing = CandidateGenerationOperationV1.model_validate(existing_snap.to_dict())
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)
            if existing.status is CandidateGenerationStatusV1.completed:
                result_box["result"] = GenerateBeginCompleted(candidate_id=existing.candidate_id)
                return
            if existing.status is CandidateGenerationStatusV1.failed:
                if existing.failure is None:
                    raise PersistenceUnavailableError()
                result_box["result"] = GenerateBeginFailed(failure=existing.failure)
                return
            if existing.lease_expires_at > now:
                result_box["result"] = GenerateBeginInProgress(
                    candidate_id=existing.candidate_id,
                    lease_expires_at=existing.lease_expires_at,
                )
                return

            claimed = existing.model_copy(
                update={
                    "lease_owner": lease_owner,
                    "lease_expires_at": now + timedelta(seconds=lease_duration_seconds),
                    "attempt_count": existing.attempt_count + 1,
                    "updated_at": now,
                }
            )
            transaction.set(op_ref, _dump(claimed))
            result_box["result"] = GenerateBeginClaimed(operation=claimed)

        try:
            operation_fn(self._client.transaction())
        except IdempotencyConflictError:
            raise
        except PersistenceUnavailableError:
            raise
        except Exception as error:
            if _is_already_exists(error):
                # Concurrent first-create: re-enter begin semantics via re-read.
                return self.begin_generate(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    candidate_id_factory=candidate_id_factory,
                    lease_owner=lease_owner,
                    lease_duration_seconds=lease_duration_seconds,
                )
            raise PersistenceUnavailableError() from error
        return result_box["result"]

    def complete_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        candidate: GeneratedStatblockCandidateV1,
    ) -> GeneratedStatblockCandidateV1:
        from google.cloud.firestore_v1 import transactional

        op_ref = self._operation_document(caller_scope, request_id)
        candidate_ref = self._client.collection(self._candidates_collection).document(
            candidate.candidate_id
        )
        result_box: dict[str, GeneratedStatblockCandidateV1] = {}

        @transactional
        def operation_fn(transaction):
            now = self._clock()
            existing_snap = op_ref.get(transaction=transaction)
            if not existing_snap.exists:
                raise PersistenceUnavailableError()
            existing = CandidateGenerationOperationV1.model_validate(existing_snap.to_dict())
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)
            if candidate.candidate_id != existing.candidate_id:
                raise ImmutableResourceConflictError("candidate", candidate.candidate_id)

            if existing.status is CandidateGenerationStatusV1.failed:
                raise ImmutableResourceConflictError("candidate", existing.candidate_id)

            candidate_snap = candidate_ref.get(transaction=transaction)
            if existing.status is CandidateGenerationStatusV1.completed or candidate_snap.exists:
                if candidate_snap.exists:
                    stored = GeneratedStatblockCandidateV1.model_validate(candidate_snap.to_dict())
                else:
                    raise PersistenceUnavailableError()
                if existing.status is not CandidateGenerationStatusV1.completed:
                    transaction.set(
                        op_ref,
                        _dump(
                            existing.model_copy(
                                update={
                                    "status": CandidateGenerationStatusV1.completed,
                                    "updated_at": now,
                                    "completed_at": now,
                                    "failure": None,
                                }
                            )
                        ),
                    )
                result_box["result"] = stored
                return

            stored = candidate.model_copy(deep=True)
            transaction.create(candidate_ref, _dump(stored))
            transaction.set(
                op_ref,
                _dump(
                    existing.model_copy(
                        update={
                            "status": CandidateGenerationStatusV1.completed,
                            "updated_at": now,
                            "completed_at": now,
                            "failure": None,
                        }
                    )
                ),
            )
            result_box["result"] = stored

        try:
            operation_fn(self._client.transaction())
        except (
            IdempotencyConflictError,
            ImmutableResourceConflictError,
            PersistenceUnavailableError,
        ):
            raise
        except Exception as error:
            # Indeterminate: reconcile from durable operation + candidate.
            reconciled = self._reconcile_complete(
                caller_scope=caller_scope,
                request_id=request_id,
                request_digest=request_digest,
                candidate_id=candidate.candidate_id,
            )
            if reconciled is not None:
                return reconciled
            if _is_already_exists(error):
                reconciled = self._reconcile_complete(
                    caller_scope=caller_scope,
                    request_id=request_id,
                    request_digest=request_digest,
                    candidate_id=candidate.candidate_id,
                )
                if reconciled is not None:
                    return reconciled
            raise TransactionIndeterminateError() from error
        return result_box["result"]

    def fail_generate(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        lease_owner: str,
        failure: CandidateGenerationFailureSnapshotV1,
    ) -> CandidateGenerationFailureSnapshotV1:
        from google.cloud.firestore_v1 import transactional

        op_ref = self._operation_document(caller_scope, request_id)
        result_box: dict[str, CandidateGenerationFailureSnapshotV1] = {}

        @transactional
        def operation_fn(transaction):
            now = self._clock()
            existing_snap = op_ref.get(transaction=transaction)
            if not existing_snap.exists:
                raise PersistenceUnavailableError()
            existing = CandidateGenerationOperationV1.model_validate(existing_snap.to_dict())
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(request_id)

            if existing.status is CandidateGenerationStatusV1.completed:
                raise ImmutableResourceConflictError("candidate", existing.candidate_id)
            if existing.status is CandidateGenerationStatusV1.failed:
                if existing.failure is None:
                    raise PersistenceUnavailableError()
                result_box["result"] = existing.failure
                return

            if existing.lease_owner != lease_owner:
                result_box["result"] = failure
                return

            snapshot = failure.model_copy(deep=True)
            transaction.set(
                op_ref,
                _dump(
                    existing.model_copy(
                        update={
                            "status": CandidateGenerationStatusV1.failed,
                            "failure": snapshot,
                            "updated_at": now,
                            "completed_at": now,
                        }
                    )
                ),
            )
            result_box["result"] = snapshot

        try:
            operation_fn(self._client.transaction())
        except (
            IdempotencyConflictError,
            ImmutableResourceConflictError,
            PersistenceUnavailableError,
        ):
            raise
        except Exception as error:
            record = self.get_generate_operation(caller_scope, request_id)
            if record is not None and record.status is CandidateGenerationStatusV1.failed:
                if record.request_digest != request_digest:
                    raise IdempotencyConflictError(request_id) from error
                if record.failure is not None:
                    return record.failure
            raise TransactionIndeterminateError() from error
        return result_box["result"]

    def _reconcile_complete(
        self,
        *,
        caller_scope: str,
        request_id: str,
        request_digest: str,
        candidate_id: str,
    ) -> GeneratedStatblockCandidateV1 | None:
        try:
            record = self.get_generate_operation(caller_scope, request_id)
        except PersistenceUnavailableError:
            return None
        if record is None:
            return None
        if record.request_digest != request_digest:
            raise IdempotencyConflictError(request_id)
        if record.candidate_id != candidate_id:
            raise ImmutableResourceConflictError("candidate", candidate_id)
        if record.status is CandidateGenerationStatusV1.completed:
            try:
                snapshot = (
                    self._client.collection(self._candidates_collection)
                    .document(candidate_id)
                    .get()
                )
            except Exception as error:
                raise PersistenceUnavailableError() from error
            if snapshot.exists:
                return GeneratedStatblockCandidateV1.model_validate(snapshot.to_dict())
            raise PersistenceUnavailableError()
        if record.status is CandidateGenerationStatusV1.failed:
            raise ImmutableResourceConflictError("candidate", candidate_id)
        return None

    def _operation_document(self, caller_scope: str, request_id: str) -> Any:
        import hashlib

        digest = hashlib.sha256(
            f"{caller_scope}\x1f{GENERATE_CANDIDATE_OPERATION}\x1f{request_id}".encode()
        ).hexdigest()
        return self._client.collection(self._generate_ops_collection).document(digest)


class FirestoreStatblockPersistenceRepository:
    """Atomic create/append adapter using Firestore read-write transactions."""

    def __init__(
        self,
        client: Any,
        *,
        clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[str], str] | None = None,
        statblocks_collection: str = STATBLOCKS_COLLECTION,
        idempotency_collection: str = IDEMPOTENCY_COLLECTION,
    ) -> None:
        self._client, self._clock = client, clock
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid4().hex}")
        self._statblocks_collection = statblocks_collection
        self._idempotency_collection = idempotency_collection

    def get(self, statblock_id: str) -> StatblockResourceV1:
        try:
            snapshot = self._document(self._statblocks_collection, statblock_id).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            raise StatblockNotFoundError(statblock_id)
        return StatblockResourceV1.model_validate(snapshot.to_dict())

    def get_revision(self, statblock_id: str, revision_id: str) -> StatblockRevisionResourceV1:
        try:
            if not self._document(self._statblocks_collection, statblock_id).get().exists:
                raise StatblockNotFoundError(statblock_id)
            snapshot = self._revision_document(statblock_id, revision_id).get()
        except StatblockNotFoundError:
            raise
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            raise RevisionNotFoundError(revision_id)
        return StatblockRevisionResourceV1.model_validate(snapshot.to_dict())

    def list_for_statblock(self, statblock_id: str) -> list[StatblockRevisionResourceV1]:
        try:
            if not self._document(self._statblocks_collection, statblock_id).get().exists:
                raise StatblockNotFoundError(statblock_id)
            snapshots = list(
                self._document(self._statblocks_collection, statblock_id).collection("revisions").stream()
            )
        except StatblockNotFoundError:
            raise
        except Exception as error:
            raise PersistenceUnavailableError() from error
        return [
            StatblockRevisionResourceV1.model_validate(snapshot.to_dict())
            for snapshot in snapshots
        ]

    def get_idempotency(
        self, caller_scope: str, operation: str, idempotency_key: str
    ) -> IdempotencyRecordV1 | None:
        try:
            snapshot = self._idempotency_document(caller_scope, operation, idempotency_key).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            return None
        return IdempotencyRecordV1.model_validate(snapshot.to_dict())

    def create_statblock(
        self, command: CreateStatblockCommand
    ) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]:
        request_digest = command.request_digest
        definition = command.definition
        provenance = command.provenance
        asset_bindings = command.asset_bindings
        existing = self.get_idempotency(
            command.caller_scope, "create_statblock", command.idempotency_key
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(command.idempotency_key)
            return (
                self.get(existing.outcome.statblock_id),
                self.get_revision(existing.outcome.statblock_id, existing.outcome.revision_id),
            )

        canonical, digest, receipt = _persistence_material(definition)
        now = self._clock()
        statblock_id = self._id_factory("sb")
        revision_id = self._id_factory("rev")
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
        outcome = IdempotencyOutcomeV1(statblock_id=statblock_id, revision_id=revision_id)
        try:
            self._transactional_write(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                request_digest,
                outcome,
                [
                    (self._document(self._statblocks_collection, statblock_id), _dump(statblock)),
                    (self._revision_document(statblock_id, revision_id), _dump(revision)),
                ],
                already_exists=ImmutableResourceConflictError("statblock", statblock_id),
            )
        except TransactionIndeterminateError:
            reconciled = self._reconcile_idempotent_outcome(
                command.caller_scope,
                "create_statblock",
                command.idempotency_key,
                request_digest,
            )
            return (
                self.get(reconciled.statblock_id),
                self.get_revision(reconciled.statblock_id, reconciled.revision_id),
            )
        record = self.get_idempotency(
            command.caller_scope, "create_statblock", command.idempotency_key
        )
        if record is not None and record.outcome != outcome:
            return (
                self.get(record.outcome.statblock_id),
                self.get_revision(record.outcome.statblock_id, record.outcome.revision_id),
            )
        return statblock, revision

    def append_revision(self, command: AppendRevisionCommand) -> StatblockRevisionResourceV1:
        request_digest = command.request_digest
        definition = command.definition
        provenance = command.provenance
        asset_bindings = command.asset_bindings
        existing = self.get_idempotency(
            command.caller_scope, "append_revision", command.idempotency_key
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise IdempotencyConflictError(command.idempotency_key)
            return self.get_revision(existing.outcome.statblock_id, existing.outcome.revision_id)

        canonical, digest, receipt = _persistence_material(definition)
        now = self._clock()
        revision_id = self._id_factory("rev")
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
        try:
            self._transactional_append(command, revision, request_digest=request_digest)
        except TransactionIndeterminateError:
            reconciled = self._reconcile_idempotent_outcome(
                command.caller_scope,
                "append_revision",
                command.idempotency_key,
                request_digest,
            )
            return self.get_revision(reconciled.statblock_id, reconciled.revision_id)
        record = self.get_idempotency(
            command.caller_scope, "append_revision", command.idempotency_key
        )
        if record is not None and record.outcome.revision_id != revision_id:
            return self.get_revision(record.outcome.statblock_id, record.outcome.revision_id)
        return revision

    def _transactional_write(
        self,
        scope: str,
        operation: str,
        key: str,
        digest: str,
        outcome: IdempotencyOutcomeV1,
        writes: list[tuple[Any, dict]],
        *,
        already_exists: Exception,
    ) -> None:
        from google.cloud.firestore_v1 import transactional

        idem_ref = self._idempotency_document(scope, operation, key)

        @transactional
        def operation_fn(transaction):
            existing = idem_ref.get(transaction=transaction)
            if existing.exists:
                record = IdempotencyRecordV1.model_validate(existing.to_dict())
                if record.request_digest != digest:
                    raise IdempotencyConflictError(key)
                return
            for document, data in writes:
                transaction.create(document, data)
            transaction.create(
                idem_ref,
                _dump(
                    IdempotencyRecordV1(
                        caller_scope=scope,
                        operation=operation,
                        idempotency_key=key,
                        request_digest=digest,
                        outcome=outcome,
                        created_at=self._clock(),
                    )
                ),
            )

        self._run_transaction(operation_fn, already_exists=already_exists)

    def _transactional_append(
        self,
        command: AppendRevisionCommand,
        revision: StatblockRevisionResourceV1,
        *,
        request_digest: str,
    ) -> None:
        from google.cloud.firestore_v1 import transactional

        idem_ref = self._idempotency_document(
            command.caller_scope, "append_revision", command.idempotency_key
        )
        statblock_ref = self._document(self._statblocks_collection, command.statblock_id)
        parent_ref = self._revision_document(command.statblock_id, command.parent_revision_id)
        revision_ref = self._revision_document(command.statblock_id, revision.revision_id)

        @transactional
        def operation_fn(transaction):
            existing = idem_ref.get(transaction=transaction)
            if existing.exists:
                record = IdempotencyRecordV1.model_validate(existing.to_dict())
                if record.request_digest != request_digest:
                    raise IdempotencyConflictError(command.idempotency_key)
                return

            statblock_snap = statblock_ref.get(transaction=transaction)
            if not statblock_snap.exists:
                raise StatblockNotFoundError(command.statblock_id)
            statblock = StatblockResourceV1.model_validate(statblock_snap.to_dict())

            parent_snap = parent_ref.get(transaction=transaction)
            if not parent_snap.exists:
                raise ParentRevisionMismatchError(
                    command.statblock_id, command.parent_revision_id
                )
            if statblock.latest_revision_id != command.parent_revision_id:
                raise StaleParentRevisionError(
                    command.statblock_id,
                    command.parent_revision_id,
                    statblock.latest_revision_id,
                )

            transaction.create(revision_ref, _dump(revision))
            transaction.update(statblock_ref, {"latest_revision_id": revision.revision_id})
            transaction.create(
                idem_ref,
                _dump(
                    IdempotencyRecordV1(
                        caller_scope=command.caller_scope,
                        operation="append_revision",
                        idempotency_key=command.idempotency_key,
                        request_digest=request_digest,
                        outcome=IdempotencyOutcomeV1(
                            statblock_id=command.statblock_id,
                            revision_id=revision.revision_id,
                        ),
                        created_at=self._clock(),
                    )
                ),
            )

        self._run_transaction(
            operation_fn,
            already_exists=ImmutableRevisionConflictError(revision.revision_id),
        )

    def _reconcile_idempotent_outcome(
        self, scope: str, operation: str, key: str, digest: str
    ) -> IdempotencyOutcomeV1:
        """Resolve an uncertain commit via the durable idempotency record."""

        try:
            record = self.get_idempotency(scope, operation, key)
        except PersistenceUnavailableError as error:
            raise TransactionIndeterminateError() from error
        if record is None:
            raise TransactionIndeterminateError()
        if record.request_digest != digest:
            raise IdempotencyConflictError(key)
        return record.outcome

    def _run_transaction(
        self, operation: Any, *, already_exists: Exception
    ) -> None:
        known = (
            IdempotencyConflictError,
            ParentRevisionMismatchError,
            StaleParentRevisionError,
            StatblockNotFoundError,
            ImmutableRevisionConflictError,
            ImmutableResourceConflictError,
        )
        try:
            operation(self._client.transaction())
        except known:
            raise
        except Exception as error:
            if _is_already_exists(error):
                raise already_exists from error
            # Deadline/transport/retry failures may arrive after commit. Treat every
            # non-domain transaction failure as indeterminate so callers reconcile.
            raise TransactionIndeterminateError() from error

    def _document(self, collection: str, document_id: str) -> Any:
        return self._client.collection(collection).document(document_id)

    def _revision_document(self, statblock_id: str, revision_id: str) -> Any:
        return self._document(self._statblocks_collection, statblock_id).collection("revisions").document(
            revision_id
        )

    def _idempotency_document(self, scope: str, operation: str, key: str) -> Any:
        import hashlib

        digest = hashlib.sha256(f"{scope}\x1f{operation}\x1f{key}".encode()).hexdigest()
        return self._document(self._idempotency_collection, digest)


def _dump(model: Any) -> dict[str, Any]:
    """Encode models for Firestore while preserving native timestamp fields.

    ``model_dump(mode="json")`` stringifies datetimes and breaks TTL policies that
    require a timestamp on ``expires_at``. Canonical definition text remains an
    exact string.
    """

    return _firestore_encode(model.model_dump(mode="python"))


def _firestore_encode(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, AnyUrl) or type(value).__name__ == "Url":
        # Pydantic HttpUrl dumps as Url under mode="python"; Firestore needs strings.
        return str(value)
    if isinstance(value, dict):
        return {str(key): _firestore_encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_firestore_encode(item) for item in value]
    return value


def _is_already_exists(error: Exception) -> bool:
    name = type(error).__name__
    if name in {"AlreadyExists", "Conflict"}:
        return True
    return "already exists" in str(error).lower()
