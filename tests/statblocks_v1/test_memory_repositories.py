from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CreateStatblockCommand,
    compute_request_digest,
)
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    CandidateExpiredError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    ParentRevisionMismatchError,
    StaleParentRevisionError,
    StatblockNotFoundError,
)
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition
from statblocks_v1.infrastructure.memory_repositories import (
    DeterministicIdFactory,
    InMemoryCandidateRepository,
    InMemoryStatblockPersistenceRepository,
)


def _clock():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _repository(id_factory=None):
    return InMemoryStatblockPersistenceRepository(
        clock=_clock, id_factory=id_factory or DeterministicIdFactory()
    )


def _create(definition, key="create-1", created_by="dungeonbuddy", **kwargs):
    return CreateStatblockCommand(
        caller_scope="dungeonbuddy",
        idempotency_key=key,
        definition=definition,
        created_by=created_by,
        **kwargs,
    )


def _append(definition, statblock_id, parent_revision_id, key="append-1", **kwargs):
    return AppendRevisionCommand(
        caller_scope="dungeonbuddy",
        idempotency_key=key,
        statblock_id=statblock_id,
        parent_revision_id=parent_revision_id,
        definition=definition,
        **kwargs,
    )


def test_create_append_replay_and_immutable_history(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition))
    second = repository.append_revision(
        _append(definition, statblock.statblock_id, first.revision_id)
    )
    replay = repository.append_revision(
        _append(definition, statblock.statblock_id, first.revision_id)
    )

    assert replay.revision_id == second.revision_id
    assert repository.get(statblock.statblock_id).latest_revision_id == second.revision_id
    assert repository.get_revision(statblock.statblock_id, first.revision_id) == first
    assert first.definition_digest == second.definition_digest
    assert first.canonical_definition == str(canonicalize_definition(definition))
    assert first.definition_digest == compute_definition_digest(definition)
    assert first.validation_receipt.definition_digest == first.definition_digest


def test_create_retry_after_append_returns_original_revision(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition, key="create-1"))
    repository.append_revision(
        _append(definition, statblock.statblock_id, first.revision_id, key="append-1")
    )

    replay_statblock, replay_revision = repository.create_statblock(
        _create(definition, key="create-1")
    )

    assert replay_statblock.statblock_id == statblock.statblock_id
    assert replay_revision.revision_id == first.revision_id
    assert replay_revision.parent_revision_id is None
    assert repository.get(statblock.statblock_id).latest_revision_id != first.revision_id


def test_stale_parent_append_rejected_without_writing(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition))
    second = repository.append_revision(
        _append(definition, statblock.statblock_id, first.revision_id, key="append-a")
    )

    with pytest.raises(StaleParentRevisionError):
        repository.append_revision(
            _append(definition, statblock.statblock_id, first.revision_id, key="append-b")
        )

    assert repository.get(statblock.statblock_id).latest_revision_id == second.revision_id
    assert repository.get_idempotency("dungeonbuddy", "append_revision", "append-b") is None
    assert len(repository.list_for_statblock(statblock.statblock_id)) == 2


def test_missing_statblock_parent_and_foreign_parent_are_distinct(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    first_block, first = repository.create_statblock(_create(definition, key="a"))
    second_block, second = repository.create_statblock(_create(definition, key="b"))

    with pytest.raises(StatblockNotFoundError):
        repository.append_revision(
            _append(definition, "sb_missing", first.revision_id, key="append-missing")
        )
    with pytest.raises(ParentRevisionMismatchError):
        repository.append_revision(
            _append(
                definition,
                first_block.statblock_id,
                "rev_999999",
                key="append-missing-parent",
            )
        )
    with pytest.raises(ParentRevisionMismatchError):
        repository.append_revision(
            _append(
                definition,
                first_block.statblock_id,
                second.revision_id,
                key="append-foreign-parent",
            )
        )


def test_idempotency_conflict_and_canonical_request_digest(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    repository.create_statblock(_create(definition, key="create-1"))

    with pytest.raises(IdempotencyConflictError):
        repository.create_statblock(
            _create(definition, key="create-1", created_by="other-service")
        )

    payload = load_fixture("simple_bruiser")
    payload["identity"]["name"] = "Café"
    composed = StatblockDefinitionV1.model_validate(payload)
    payload["identity"]["name"] = "Cafe\u0301"
    decomposed = StatblockDefinitionV1.model_validate(payload)
    assert _create(composed).request_digest == _create(decomposed).request_digest

    with_subtypes = definition.model_copy(
        update={
            "identity": definition.identity.model_copy(
                update={"subtypes": ["fiend", "demon"]}
            )
        }
    )
    reordered = with_subtypes.model_copy(
        update={
            "identity": with_subtypes.identity.model_copy(
                update={"subtypes": ["demon", "fiend"]}
            )
        }
    )
    assert _create(with_subtypes).request_digest == _create(reordered).request_digest

    changed = _create(definition, provenance={"note": "x"})
    assert changed.request_digest != _create(definition).request_digest
    assert compute_request_digest("create_statblock", {"x": 1}).startswith("sha256:")


def test_caller_mutation_cannot_alter_stored_revision(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    expected_canonical = str(canonicalize_definition(definition))
    expected_digest = compute_definition_digest(definition)
    repository = _repository()
    command = _create(
        definition,
        provenance={"source": "test"},
        asset_bindings=[{"asset_id": "img_1"}],
    )
    _, revision = repository.create_statblock(command)

    command.definition.identity.name = "Mutated After Store"
    command.provenance["source"] = "mutated"
    command.asset_bindings[0]["asset_id"] = "img_mutated"
    returned = repository.get_revision(revision.statblock_id, revision.revision_id)
    returned.definition.identity.name = "Mutated Returned Copy"
    returned.provenance["source"] = "returned-mutated"

    stored = repository.get_revision(revision.statblock_id, revision.revision_id)
    assert stored.definition.identity.name == "Ironhide Brute"
    assert stored.provenance == {"source": "test"}
    assert stored.asset_bindings == [{"asset_id": "img_1"}]
    assert stored.canonical_definition == expected_canonical
    assert stored.definition_digest == expected_digest
    assert compute_definition_digest(stored.definition) == stored.definition_digest


def test_id_collisions_cannot_overwrite_history(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    class CollisionFactory:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, prefix: str) -> str:
            self.calls += 1
            if prefix == "sb":
                return "sb_fixed01"
            return "rev_fixed01"

    repository = _repository(id_factory=CollisionFactory())
    repository.create_statblock(_create(definition, key="first"))
    with pytest.raises(ImmutableResourceConflictError):
        repository.create_statblock(_create(definition, key="second"))

    candidate_repo = InMemoryCandidateRepository(clock=_clock)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_000001",
        definition=definition,
        validation_receipt=validate_definition(
            definition, ValidationMode.generation_candidate
        ),
        created_at=_clock(),
        expires_at=_clock() + timedelta(minutes=1),
    )
    candidate_repo.create(candidate)
    with pytest.raises(ImmutableResourceConflictError):
        candidate_repo.create(candidate)

    # Forced revision collision on append.
    class RevisionCollisionFactory:
        def __init__(self) -> None:
            self.n = 0

        def __call__(self, prefix: str) -> str:
            self.n += 1
            if prefix == "sb":
                return f"sb_{self.n:06d}"
            return "rev_dup001"

    colliding = _repository(id_factory=RevisionCollisionFactory())
    statblock, first = colliding.create_statblock(_create(definition, key="c1"))
    with pytest.raises(ImmutableRevisionConflictError):
        colliding.append_revision(
            _append(definition, statblock.statblock_id, first.revision_id, key="a1")
        )


def test_candidate_expiration(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    created = _clock()
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_000001",
        definition=definition,
        validation_receipt=validate_definition(
            definition, ValidationMode.generation_candidate
        ),
        created_at=created,
        expires_at=created + timedelta(minutes=1),
    )
    repository = InMemoryCandidateRepository(clock=_clock)
    repository.create(candidate)
    with pytest.raises(CandidateExpiredError):
        repository.get(candidate.candidate_id, now=created + timedelta(minutes=1))


def test_digest_api_still_rejects_non_definition_inputs(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    canonical = canonicalize_definition(definition)
    with pytest.raises(TypeError):
        compute_definition_digest(str(canonical))
    with pytest.raises(TypeError):
        compute_definition_digest(canonical)
    with pytest.raises(TypeError):
        compute_definition_digest(str(canonical).encode("utf-8"))
