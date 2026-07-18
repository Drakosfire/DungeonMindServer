from datetime import datetime, timedelta, timezone

import pytest

from statblocks_v1.application.repositories import AppendRevisionCommand, CreateStatblockCommand
from statblocks_v1.domain.errors import CandidateExpiredError, IdempotencyConflictError, ParentRevisionMismatchError
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition
from statblocks_v1.infrastructure.memory_repositories import (
    DeterministicIdFactory, InMemoryCandidateRepository, InMemoryStatblockPersistenceRepository,
)


def _clock():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _repository():
    return InMemoryStatblockPersistenceRepository(clock=_clock, id_factory=DeterministicIdFactory())


def _create(definition, key="create-1", created_by="dungeonbuddy"):
    return CreateStatblockCommand(
        caller_scope="dungeonbuddy", idempotency_key=key, definition=definition, created_by=created_by
    )


def test_create_append_replay_and_immutable_history(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition))
    second = repository.append_revision(AppendRevisionCommand(
        caller_scope="dungeonbuddy", idempotency_key="append-1", statblock_id=statblock.statblock_id,
        parent_revision_id=first.revision_id, definition=definition,
    ))
    replay = repository.append_revision(AppendRevisionCommand(
        caller_scope="dungeonbuddy", idempotency_key="append-1", statblock_id=statblock.statblock_id,
        parent_revision_id=first.revision_id, definition=definition,
    ))

    assert replay.revision_id == second.revision_id
    assert repository.get(statblock.statblock_id).latest_revision_id == second.revision_id
    assert repository.get_revision(statblock.statblock_id, first.revision_id) == first
    assert first.definition_digest == second.definition_digest  # same mechanics can be intentionally accepted twice


def test_idempotency_conflict_and_parent_mismatch(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition))
    with pytest.raises(IdempotencyConflictError):
        repository.create_statblock(_create(definition, key="create-1", created_by="other-service"))
    with pytest.raises(ParentRevisionMismatchError):
        repository.append_revision(AppendRevisionCommand(
            caller_scope="dungeonbuddy", idempotency_key="append-1", statblock_id=statblock.statblock_id,
            parent_revision_id="rev_999999", definition=definition,
        ))


def test_candidate_expiration(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    created = _clock()
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_000001", definition=definition,
        validation_receipt=validate_definition(definition, ValidationMode.generation_candidate),
        created_at=created, expires_at=created + timedelta(minutes=1),
    )
    repository = InMemoryCandidateRepository(clock=_clock)
    repository.create(candidate)
    with pytest.raises(CandidateExpiredError):
        repository.get(candidate.candidate_id, now=created + timedelta(minutes=1))
