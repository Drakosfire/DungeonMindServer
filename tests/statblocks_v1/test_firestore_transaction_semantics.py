"""Unit coverage for Firestore transaction failure classification and reconciliation.

These tests do not require the emulator; they inject commit-then-error behavior at
the repository seam used by create/append.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from statblocks_v1.application.repositories import AppendRevisionCommand, CreateStatblockCommand
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    PersistenceUnavailableError,
    TransactionIndeterminateError,
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
from statblocks_v1.infrastructure.firestore_repositories import (
    FirestoreCandidateRepository,
    FirestoreStatblockPersistenceRepository,
)
from statblocks_v1.infrastructure.memory_repositories import DeterministicIdFactory


def _clock():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class _FakeClient:
    """Minimal client so `_document` / `_run_transaction` can be unit-tested."""

    def transaction(self):
        return object()

    def collection(self, name: str):
        return SimpleNamespace(
            document=lambda document_id: SimpleNamespace(
                path=f"{name}/{document_id}",
                collection=lambda sub: SimpleNamespace(
                    document=lambda sub_id: SimpleNamespace(path=f"{name}/{document_id}/{sub}/{sub_id}")
                ),
            )
        )


class _DeadlineExceeded(Exception):
    """Stand-in for google.api_core.exceptions.DeadlineExceeded."""


def test_run_transaction_maps_deadline_to_indeterminate_not_unavailable():
    repository = FirestoreStatblockPersistenceRepository(client=_FakeClient(), clock=_clock)

    def boom(_transaction):
        raise _DeadlineExceeded("deadline exceeded")

    with pytest.raises(TransactionIndeterminateError):
        repository._run_transaction(
            boom,
            already_exists=ImmutableResourceConflictError("statblock", "sb_x"),
        )


def test_run_transaction_maps_already_exists_to_provided_typed_error():
    repository = FirestoreStatblockPersistenceRepository(client=_FakeClient(), clock=_clock)

    class AlreadyExists(Exception):
        pass

    def boom(_transaction):
        raise AlreadyExists("document already exists")

    with pytest.raises(ImmutableResourceConflictError) as exc:
        repository._run_transaction(
            boom,
            already_exists=ImmutableResourceConflictError("statblock", "sb_fixed01"),
        )
    assert exc.value.details == {
        "resource_type": "statblock",
        "resource_id": "sb_fixed01",
    }

    with pytest.raises(ImmutableRevisionConflictError) as rev_exc:
        repository._run_transaction(
            boom,
            already_exists=ImmutableRevisionConflictError("rev_fixed01"),
        )
    assert rev_exc.value.details == {"revision_id": "rev_fixed01"}


def test_create_reconciles_exact_outcome_after_indeterminate_commit(load_fixture, monkeypatch):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    factory = DeterministicIdFactory()
    repository = FirestoreStatblockPersistenceRepository(
        client=_FakeClient(), clock=_clock, id_factory=factory
    )
    command = CreateStatblockCommand(
        caller_scope="dungeonbuddy",
        idempotency_key="reconcile-create",
        definition=definition,
        created_by="dungeonbuddy",
    )
    expected_statblock_id = "sb_000001"
    expected_revision_id = "rev_000002"
    receipt = validate_definition(definition, ValidationMode.persistence)
    canonical = str(canonicalize_definition(definition))
    digest = compute_definition_digest(definition)
    stored_statblock = StatblockResourceV1(
        statblock_id=expected_statblock_id,
        latest_revision_id=expected_revision_id,
        created_at=_clock(),
        created_by="dungeonbuddy",
    )
    stored_revision = StatblockRevisionResourceV1(
        statblock_id=expected_statblock_id,
        revision_id=expected_revision_id,
        definition=definition,
        canonical_definition=canonical,
        definition_digest=digest,
        validation_receipt=receipt,
        created_at=_clock(),
    )
    record = IdempotencyRecordV1(
        caller_scope="dungeonbuddy",
        operation="create_statblock",
        idempotency_key="reconcile-create",
        request_digest=command.request_digest,
        outcome=IdempotencyOutcomeV1(
            statblock_id=expected_statblock_id, revision_id=expected_revision_id
        ),
        created_at=_clock(),
    )

    calls = {"n": 0}

    def get_idempotency(scope, operation, key):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return record

    monkeypatch.setattr(repository, "get_idempotency", get_idempotency)
    monkeypatch.setattr(
        repository,
        "_transactional_write",
        lambda *args, **kwargs: (_ for _ in ()).throw(TransactionIndeterminateError()),
    )
    monkeypatch.setattr(repository, "get", lambda sid: stored_statblock)
    monkeypatch.setattr(repository, "get_revision", lambda sid, rid: stored_revision)

    statblock, revision = repository.create_statblock(command)
    assert statblock.statblock_id == expected_statblock_id
    assert revision.revision_id == expected_revision_id
    assert factory._sequence == 2


def test_create_indeterminate_when_reconcile_read_unavailable(load_fixture, monkeypatch):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = FirestoreStatblockPersistenceRepository(
        client=_FakeClient(), clock=_clock, id_factory=DeterministicIdFactory()
    )
    command = CreateStatblockCommand(
        caller_scope="dungeonbuddy",
        idempotency_key="reconcile-unavailable",
        definition=definition,
        created_by="dungeonbuddy",
    )

    calls = {"n": 0}

    def get_idempotency(scope, operation, key):
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        raise PersistenceUnavailableError()

    monkeypatch.setattr(repository, "get_idempotency", get_idempotency)
    monkeypatch.setattr(
        repository,
        "_transactional_write",
        lambda *args, **kwargs: (_ for _ in ()).throw(TransactionIndeterminateError()),
    )

    with pytest.raises(TransactionIndeterminateError):
        repository.create_statblock(command)


def test_append_already_exists_uses_revision_id(load_fixture, monkeypatch):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = FirestoreStatblockPersistenceRepository(
        client=_FakeClient(), clock=_clock, id_factory=DeterministicIdFactory()
    )
    command = AppendRevisionCommand(
        caller_scope="dungeonbuddy",
        idempotency_key="append-collision",
        statblock_id="sb_000001",
        parent_revision_id="rev_000001",
        definition=definition,
    )

    monkeypatch.setattr(repository, "get_idempotency", lambda *args, **kwargs: None)

    def append_collision(cmd, revision, *, request_digest):
        raise ImmutableRevisionConflictError(revision.revision_id)

    monkeypatch.setattr(repository, "_transactional_append", append_collision)

    with pytest.raises(ImmutableRevisionConflictError) as exc:
        repository.append_revision(command)
    assert exc.value.details == {"revision_id": "rev_000001"}


def test_candidate_create_maps_client_failures_to_persistence_unavailable(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    class _DeadlineExceeded(Exception):
        pass

    class _FailingCollection:
        def document(self, _candidate_id: str):
            return SimpleNamespace(
                create=lambda _payload: (_ for _ in ()).throw(
                    _DeadlineExceeded("deadline exceeded")
                )
            )

    client = SimpleNamespace(collection=lambda _name: _FailingCollection())
    repository = FirestoreCandidateRepository(client, clock=_clock)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_fail001",
        definition=definition,
        validation_receipt=validate_definition(
            definition, ValidationMode.generation_candidate
        ),
        created_at=_clock(),
        expires_at=_clock(),
    )

    with pytest.raises(PersistenceUnavailableError):
        repository.create(candidate)
