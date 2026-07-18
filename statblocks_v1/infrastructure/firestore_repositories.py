"""Synchronous Firestore adapters for immutable statblock v1 persistence.

Callers in async code must use ``await asyncio.to_thread(repository.method, ...)``.
The adapter deliberately does not expose async-looking methods that could block
the event loop.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from statblocks_v1.application.repositories import AppendRevisionCommand, CreateStatblockCommand
from statblocks_v1.domain.errors import (
    CandidateExpiredError, CandidateNotFoundError, IdempotencyConflictError,
    ParentRevisionMismatchError, PersistenceUnavailableError, RevisionNotFoundError,
    StatblockNotFoundError, TransactionIndeterminateError,
)
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1, IdempotencyRecordV1, ResourceLocatorV1,
    StatblockResourceV1, StatblockRevisionResourceV1,
)
from statblocks_v1.infrastructure.memory_repositories import (
    _persistence_material, _provenance, utc_now,
)

CANDIDATES_COLLECTION = "dungeonbuddy_statblock_candidates_v1"
STATBLOCKS_COLLECTION = "dungeonbuddy_statblocks_v1"
IDEMPOTENCY_COLLECTION = "dungeonbuddy_statblock_idempotency_v1"


class FirestoreCandidateRepository:
    """Candidate documents are mutable only for Firestore TTL deletion."""

    def __init__(self, client: Any, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._client, self._clock = client, clock

    def create(self, candidate: GeneratedStatblockCandidateV1) -> GeneratedStatblockCandidateV1:
        try:
            self._client.collection(CANDIDATES_COLLECTION).document(candidate.candidate_id).create(_dump(candidate))
        except Exception as error:
            raise PersistenceUnavailableError() from error
        return candidate.model_copy(deep=True)

    def get(self, candidate_id: str, *, now: datetime | None = None) -> GeneratedStatblockCandidateV1:
        try:
            snapshot = self._client.collection(CANDIDATES_COLLECTION).document(candidate_id).get()
        except Exception as error:
            raise PersistenceUnavailableError() from error
        if not snapshot.exists:
            raise CandidateNotFoundError(candidate_id)
        candidate = GeneratedStatblockCandidateV1.model_validate(snapshot.to_dict())
        if candidate.expires_at <= (now or self._clock()):
            raise CandidateExpiredError(candidate_id)
        return candidate


class FirestoreStatblockPersistenceRepository:
    """Atomic create/append adapter using Firestore read-write transactions."""

    def __init__(
        self, client: Any, *, clock: Callable[[], datetime] = utc_now,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._client, self._clock = client, clock
        self._id_factory = id_factory or (lambda prefix: f"{prefix}_{uuid4().hex}")

    def get(self, statblock_id: str) -> StatblockResourceV1:
        snapshot = self._document(STATBLOCKS_COLLECTION, statblock_id).get()
        if not snapshot.exists:
            raise StatblockNotFoundError(statblock_id)
        return StatblockResourceV1.model_validate(snapshot.to_dict())

    def get_revision(self, statblock_id: str, revision_id: str) -> StatblockRevisionResourceV1:
        if not self._document(STATBLOCKS_COLLECTION, statblock_id).get().exists:
            raise StatblockNotFoundError(statblock_id)
        snapshot = self._revision_document(statblock_id, revision_id).get()
        if not snapshot.exists:
            raise RevisionNotFoundError(revision_id)
        return StatblockRevisionResourceV1.model_validate(snapshot.to_dict())

    def list_for_statblock(self, statblock_id: str) -> list[StatblockRevisionResourceV1]:
        if not self._document(STATBLOCKS_COLLECTION, statblock_id).get().exists:
            raise StatblockNotFoundError(statblock_id)
        return [
            StatblockRevisionResourceV1.model_validate(snapshot.to_dict())
            for snapshot in self._document(STATBLOCKS_COLLECTION, statblock_id).collection("revisions").stream()
        ]

    def get_idempotency(self, caller_scope: str, operation: str, idempotency_key: str) -> IdempotencyRecordV1 | None:
        snapshot = self._idempotency_document(caller_scope, operation, idempotency_key).get()
        return IdempotencyRecordV1.model_validate(snapshot.to_dict()) if snapshot.exists else None

    def create_statblock(self, command: CreateStatblockCommand) -> tuple[StatblockResourceV1, StatblockRevisionResourceV1]:
        canonical, digest, receipt = _persistence_material(command.definition)
        now, statblock_id, revision_id = self._clock(), self._id_factory("sb"), self._id_factory("rev")
        statblock = StatblockResourceV1(statblock_id=statblock_id, latest_revision_id=revision_id, created_at=now, created_by=command.created_by)
        revision = StatblockRevisionResourceV1(
            statblock_id=statblock_id, revision_id=revision_id, definition=command.definition,
            canonical_definition=canonical, definition_digest=digest, validation_receipt=receipt,
            provenance=_provenance(command.provenance, command.candidate_id),
            asset_bindings=command.asset_bindings, created_at=now,
        )
        outcome = ResourceLocatorV1(resource_type="statblock", resource_id=statblock_id)
        self._transactional_write(command.caller_scope, "create_statblock", command.idempotency_key, command.request_digest,
                                  outcome, [(self._document(STATBLOCKS_COLLECTION, statblock_id), _dump(statblock)),
                                            (self._revision_document(statblock_id, revision_id), _dump(revision))])
        record = self.get_idempotency(command.caller_scope, "create_statblock", command.idempotency_key)
        if record and record.outcome != outcome:
            return self.get(record.outcome.resource_id), self.get_revision(record.outcome.resource_id, self.get(record.outcome.resource_id).latest_revision_id)
        return statblock, revision

    def append_revision(self, command: AppendRevisionCommand) -> StatblockRevisionResourceV1:
        canonical, digest, receipt = _persistence_material(command.definition)
        now, revision_id = self._clock(), self._id_factory("rev")
        revision = StatblockRevisionResourceV1(
            statblock_id=command.statblock_id, revision_id=revision_id, parent_revision_id=command.parent_revision_id,
            definition=command.definition, canonical_definition=canonical, definition_digest=digest,
            validation_receipt=receipt, provenance=_provenance(command.provenance, command.candidate_id),
            asset_bindings=command.asset_bindings, created_at=now,
        )
        statblock_ref = self._document(STATBLOCKS_COLLECTION, command.statblock_id)
        self._transactional_append(command, statblock_ref, revision)
        record = self.get_idempotency(command.caller_scope, "append_revision", command.idempotency_key)
        if record and record.outcome.resource_id != revision_id:
            return self.get_revision(command.statblock_id, record.outcome.resource_id)
        return revision

    def _transactional_write(self, scope: str, operation: str, key: str, digest: str, outcome: ResourceLocatorV1, writes: list[tuple[Any, dict]]) -> None:
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
            transaction.create(idem_ref, _dump(IdempotencyRecordV1(
                caller_scope=scope, operation=operation, idempotency_key=key, request_digest=digest,
                outcome=outcome, created_at=self._clock(),
            )))
        self._run_transaction(operation_fn)

    def _transactional_append(self, command: AppendRevisionCommand, statblock_ref: Any, revision: StatblockRevisionResourceV1) -> None:
        from google.cloud.firestore_v1 import transactional
        idem_ref = self._idempotency_document(command.caller_scope, "append_revision", command.idempotency_key)
        parent_ref = self._revision_document(command.statblock_id, command.parent_revision_id)
        revision_ref = self._revision_document(command.statblock_id, revision.revision_id)
        @transactional
        def operation_fn(transaction):
            existing = idem_ref.get(transaction=transaction)
            if existing.exists:
                record = IdempotencyRecordV1.model_validate(existing.to_dict())
                if record.request_digest != command.request_digest:
                    raise IdempotencyConflictError(command.idempotency_key)
                return
            if not statblock_ref.get(transaction=transaction).exists or not parent_ref.get(transaction=transaction).exists:
                raise ParentRevisionMismatchError(command.statblock_id, command.parent_revision_id)
            transaction.create(revision_ref, _dump(revision))
            transaction.update(statblock_ref, {"latest_revision_id": revision.revision_id})
            transaction.create(idem_ref, _dump(IdempotencyRecordV1(
                caller_scope=command.caller_scope, operation="append_revision", idempotency_key=command.idempotency_key,
                request_digest=command.request_digest, outcome=ResourceLocatorV1(resource_type="revision", resource_id=revision.revision_id),
                created_at=self._clock(),
            )))
        self._run_transaction(operation_fn)

    def _run_transaction(self, operation: Any) -> None:
        try:
            operation(self._client.transaction())
        except (IdempotencyConflictError, ParentRevisionMismatchError):
            raise
        except Exception as error:
            raise TransactionIndeterminateError() from error

    def _document(self, collection: str, document_id: str) -> Any:
        return self._client.collection(collection).document(document_id)

    def _revision_document(self, statblock_id: str, revision_id: str) -> Any:
        return self._document(STATBLOCKS_COLLECTION, statblock_id).collection("revisions").document(revision_id)

    def _idempotency_document(self, scope: str, operation: str, key: str) -> Any:
        import hashlib
        digest = hashlib.sha256(f"{scope}\x1f{operation}\x1f{key}".encode()).hexdigest()
        return self._document(IDEMPOTENCY_COLLECTION, digest)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="json")
