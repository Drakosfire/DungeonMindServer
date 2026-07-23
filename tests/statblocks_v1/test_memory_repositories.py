from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from statblocks_v1.application.repositories import (
    AppendRevisionCommand,
    CreateStatblockCommand,
    compute_request_digest,
)
from statblocks_v1.domain.assets import AssetBindingV1, AssetBriefV1, AssetRefV1
from statblocks_v1.domain.canonicalization import canonicalize_definition
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import (
    AmbiguousRequestPayloadError,
    CandidateExpiredError,
    IdempotencyConflictError,
    ImmutableResourceConflictError,
    ImmutableRevisionConflictError,
    ParentRevisionMismatchError,
    StaleParentRevisionError,
    StatblockNotFoundError,
)
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    STATBLOCK_CONTRACT,
    STATBLOCK_CONTRACT_VERSION,
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
)
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

    # NFC-equivalent values remain equivalent; NFC-colliding keys fail closed.
    assert compute_request_digest(
        "create_statblock", {"note": "Café"}
    ) == compute_request_digest("create_statblock", {"note": "Cafe\u0301"})
    with pytest.raises(AmbiguousRequestPayloadError) as ambiguous:
        compute_request_digest(
            "create_statblock",
            {"provenance": {"é": 1, "e\u0301": 2}},
        )
    assert ambiguous.value.details == {"key": "é"}
    assert compute_request_digest(
        "create_statblock", {"provenance": {"é": 1}}
    ) != compute_request_digest("create_statblock", {"provenance": {"é": 2}})


def test_caller_mutation_cannot_alter_stored_revision(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    expected_canonical = str(canonicalize_definition(definition))
    expected_digest = compute_definition_digest(definition)
    repository = _repository()
    provenance = {"source": "test"}
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    binding = AssetBindingV1(
        asset=AssetRefV1(
            asset_id="img_1",
            provider_kind="cloudflare_images",
            url="https://example.test/img_1.png",
            mime_type="image/png",
            created_at=now,
        ),
        role="portrait",
    )
    assets = [binding]
    expected_bindings = [binding.model_copy(deep=True)]
    command = _create(
        definition,
        provenance=provenance,
        asset_bindings=assets,
    )
    frozen_digest = command.request_digest

    # Mutate the caller's originals and any returned property copies before/during create.
    definition.identity.name = "Mutated Source Definition"
    provenance["source"] = "mutated-source"
    assets[0].asset.asset_id = "img_source_mutated"
    command.definition.identity.name = "Mutated Property Copy"
    command.provenance["source"] = "mutated-property"
    command.asset_bindings[0].asset.asset_id = "img_property_mutated"
    with pytest.raises(AttributeError):
        command.created_by = "hijacked"

    _, revision = repository.create_statblock(command)
    assert command.request_digest == frozen_digest

    returned = repository.get_revision(revision.statblock_id, revision.revision_id)
    returned.definition.identity.name = "Mutated Returned Copy"
    returned.provenance["source"] = "returned-mutated"

    stored = repository.get_revision(revision.statblock_id, revision.revision_id)
    assert stored.definition.identity.name == "Ironhide Brute"
    assert stored.provenance == {"source": "test"}
    assert stored.asset_bindings == expected_bindings
    assert stored.canonical_definition == expected_canonical
    assert stored.definition_digest == expected_digest
    assert stored.validation_receipt.definition_digest == expected_digest
    assert compute_definition_digest(stored.definition) == stored.definition_digest
    record = repository.get_idempotency("dungeonbuddy", "create_statblock", "create-1")
    assert record is not None
    assert record.request_digest == frozen_digest


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
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
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
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
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


def test_concurrent_candidate_creates_are_atomic(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    created = _clock()
    repository = InMemoryCandidateRepository(clock=_clock)

    def make_candidate(tag: str) -> GeneratedStatblockCandidateV1:
        return GeneratedStatblockCandidateV1(
            candidate_id="cand_shared1",
            contract=STATBLOCK_CONTRACT,
            contract_version=STATBLOCK_CONTRACT_VERSION,
            definition=definition,
            validation_receipt=validate_definition(
                definition, ValidationMode.generation_candidate
            ),
            created_at=created,
            expires_at=created + timedelta(minutes=5),
            asset_brief=AssetBriefV1(prompt=f"tag-{tag}"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(repository.create, make_candidate("a")),
            pool.submit(repository.create, make_candidate("b")),
        ]
        results = []
        errors = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001 - assert typed conflict below
                errors.append(error)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ImmutableResourceConflictError)
    assert errors[0].details == {
        "resource_type": "candidate",
        "resource_id": "cand_shared1",
    }
    stored = repository.get("cand_shared1", now=created)
    assert stored.asset_brief == results[0].asset_brief
    results[0].asset_brief.prompt = "mutated"
    assert repository.get("cand_shared1", now=created).asset_brief.prompt != "mutated"


def test_digest_api_still_rejects_non_definition_inputs(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    canonical = canonicalize_definition(definition)
    with pytest.raises(TypeError):
        compute_definition_digest(str(canonical))
    with pytest.raises(TypeError):
        compute_definition_digest(canonical)
    with pytest.raises(TypeError):
        compute_definition_digest(str(canonical).encode("utf-8"))


def test_concurrent_readers_observe_committed_state_only(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    repository = _repository()
    statblock, first = repository.create_statblock(_create(definition))
    stop = threading.Event()
    errors: list[BaseException] = []

    def writer() -> None:
        parent = first.revision_id
        for index in range(25):
            revision = repository.append_revision(
                _append(
                    definition,
                    statblock.statblock_id,
                    parent,
                    key=f"append-concurrent-{index}",
                )
            )
            parent = revision.revision_id
        stop.set()

    def reader() -> None:
        while not stop.is_set():
            try:
                current = repository.get(statblock.statblock_id)
                repository.get_revision(statblock.statblock_id, current.latest_revision_id)
                listed = repository.list_for_statblock(statblock.statblock_id)
                assert any(
                    item.revision_id == current.latest_revision_id for item in listed
                )
                repository.get_idempotency(
                    "dungeonbuddy", "create_statblock", "create-1"
                )
            except BaseException as error:  # noqa: BLE001 - collect race failures
                errors.append(error)
                stop.set()
                return

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert errors == []
    assert len(repository.list_for_statblock(statblock.statblock_id)) == 26



def test_generate_ops_reserve_complete_conflict_and_takeover(load_fixture):
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        GenerateBeginCompleted,
        GenerateBeginFailed,
        GenerateBeginInProgress,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import CandidateGenerationFailureSnapshotV1
    from statblocks_v1.domain.errors import IdempotencyConflictError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    command = GenerateStatblockCommandV1(
        request_id="req_ops",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)

    claimed = ops.begin_generate(
        caller_scope="tests",
        request_id="req_ops",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_ops1",
        lease_owner="owner-a",
        lease_duration_seconds=30,
    )
    assert isinstance(claimed, GenerateBeginClaimed)
    assert claimed.operation.candidate_id == "cand_ops1"

    assert isinstance(
        ops.begin_generate(
            caller_scope="tests",
            request_id="req_ops",
            request_digest=digest,
            candidate_id_factory=lambda: "cand_other",
            lease_owner="owner-b",
            lease_duration_seconds=30,
        ),
        GenerateBeginInProgress,
    )

    with pytest.raises(IdempotencyConflictError):
        ops.begin_generate(
            caller_scope="tests",
            request_id="req_ops",
            request_digest=compute_generate_candidate_digest(
                command.model_copy(
                    update={"source": SourceSnapshotV1(name_hint="X", description="Z")}
                )
            ),
            candidate_id_factory=lambda: "cand_other",
            lease_owner="owner-b",
            lease_duration_seconds=30,
        )

    now["t"] = now["t"] + timedelta(seconds=31)
    takeover = ops.begin_generate(
        caller_scope="tests",
        request_id="req_ops",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_should_not",
        lease_owner="owner-c",
        lease_duration_seconds=30,
    )
    assert isinstance(takeover, GenerateBeginClaimed)
    assert takeover.operation.candidate_id == "cand_ops1"
    assert takeover.operation.attempt_count == 2

    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    created = now["t"]
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_ops1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=validate_definition(
            definition, ValidationMode.generation_candidate
        ),
        generation_receipt=GenerationReceiptV1(
            request_id="req_ops",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=created,
            caller_scope="tests",
            request_digest=digest,
        ),
        created_at=created,
        expires_at=created + timedelta(minutes=5),
    )
    stored = ops.complete_generate(
        caller_scope="tests",
        request_id="req_ops",
        request_digest=digest,
        lease_owner="owner-c",
        candidate=candidate,
    )
    assert stored.candidate.candidate_id == "cand_ops1"
    assert stored.already_completed is False
    assert isinstance(
        ops.begin_generate(
            caller_scope="tests",
            request_id="req_ops",
            request_digest=digest,
            candidate_id_factory=lambda: "cand_x",
            lease_owner="owner-d",
            lease_duration_seconds=30,
        ),
        GenerateBeginCompleted,
    )

    # Stale-worker convergence: second complete returns canonical candidate as replay.
    again = ops.complete_generate(
        caller_scope="tests",
        request_id="req_ops",
        request_digest=digest,
        lease_owner="owner-stale",
        candidate=candidate.model_copy(update={"asset_brief": None}),
    )
    assert again.candidate.candidate_id == "cand_ops1"
    assert again.already_completed is True

    # Independent failure key
    fail_cmd = command.model_copy(update={"request_id": "req_fail"})
    fail_digest = compute_generate_candidate_digest(fail_cmd)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_fail",
        request_digest=fail_digest,
        candidate_id_factory=lambda: "cand_fail",
        lease_owner="owner-f",
        lease_duration_seconds=30,
    )
    snapshot = ops.fail_generate(
        caller_scope="tests",
        request_id="req_fail",
        request_digest=fail_digest,
        lease_owner="owner-f",
        failure=CandidateGenerationFailureSnapshotV1(
            kind="provider_refusal", message="nope"
        ),
    )
    assert snapshot.kind == "provider_refusal"
    failed = ops.begin_generate(
        caller_scope="tests",
        request_id="req_fail",
        request_digest=fail_digest,
        candidate_id_factory=lambda: "cand_fail2",
        lease_owner="owner-g",
        lease_duration_seconds=30,
    )
    assert isinstance(failed, GenerateBeginFailed)
    assert failed.failure.kind == "provider_refusal"


def test_generate_ops_concurrent_complete_converges(load_fixture):
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import compute_generate_candidate_digest
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_race",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_race",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_race",
        lease_owner="a",
        lease_duration_seconds=60,
    )
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)

    def make(tag: str) -> GeneratedStatblockCandidateV1:
        return GeneratedStatblockCandidateV1(
            candidate_id="cand_race",
            contract=STATBLOCK_CONTRACT,
            contract_version=STATBLOCK_CONTRACT_VERSION,
            definition=definition,
            validation_receipt=receipt,
            generation_receipt=GenerationReceiptV1(
                request_id="req_race",
                provider="test",
                model="test-model",
                prompt_version="v1",
                schema_version="v1",
                schema_fingerprint="fp",
                generated_at=now,
                caller_scope="tests",
                request_digest=digest,
            ),
            created_at=now,
            expires_at=now + timedelta(minutes=5),
            asset_brief=AssetBriefV1(prompt=tag),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                ops.complete_generate,
                caller_scope="tests",
                request_id="req_race",
                request_digest=digest,
                lease_owner="a",
                candidate=make("a"),
            ),
            pool.submit(
                ops.complete_generate,
                caller_scope="tests",
                request_id="req_race",
                request_digest=digest,
                lease_owner="b",
                candidate=make("b"),
            ),
        ]
        results = [future.result() for future in futures]
    assert {item.candidate.candidate_id for item in results} == {"cand_race"}
    assert {item.already_completed for item in results} == {False, True}
    assert len(candidates._candidates) == 1


def test_generate_ops_rejects_unrelated_candidate_document(load_fixture):
    """Same candidate_id from a different request must fail closed, not be adopted."""
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import compute_generate_candidate_digest
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_own",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_own",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_shared",
        lease_owner="owner-a",
        lease_duration_seconds=60,
    )
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    # Pre-seed an unrelated candidate that happens to share the reserved ID.
    foreign = GeneratedStatblockCandidateV1(
        candidate_id="cand_shared",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt={
            "request_id": "req_foreign",
            "provider": "test",
            "model": "test-model",
            "prompt_version": "v1",
            "schema_version": "v1",
            "schema_fingerprint": "fp",
            "generated_at": now,
            "caller_scope": "tests",
            "request_digest": "sha256:" + ("a" * 64),
        },
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(foreign)
    owned = foreign.model_copy(
        update={
            "generation_receipt": {
                "request_id": "req_own",
                "provider": "test",
                "model": "test-model",
                "prompt_version": "v1",
                "schema_version": "v1",
                "schema_fingerprint": "fp",
                "generated_at": now,
                "caller_scope": "tests",
                "request_digest": digest,
            }
        }
    )
    with pytest.raises(GenerateOperationIntegrityError):
        ops.complete_generate(
            caller_scope="tests",
            request_id="req_own",
            request_digest=digest,
            lease_owner="owner-a",
            candidate=owned,
        )


def test_generate_ops_ownership_requires_request_digest(load_fixture):
    """Same request_id/scope without matching request_digest must fail closed."""
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import (
        candidate_belongs_to_generate_operation,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_digest",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    other_digest = "sha256:" + ("b" * 64)
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    operation = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_digest",
        request_digest=digest,
        candidate_id="cand_digest",
        status=CandidateGenerationStatusV1.completed,
        lease_owner="owner",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
        completed_at=now,
        candidate_expires_at=now + timedelta(minutes=5),
        outcome_digest="sha256:" + ("f" * 64),
    )
    mismatched = GeneratedStatblockCandidateV1(
        candidate_id="cand_digest",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt=GenerationReceiptV1(
            request_id="req_digest",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="tests",
            request_digest=other_digest,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    assert candidate_belongs_to_generate_operation(mismatched, operation) is False
    candidates._create_unlocked(mismatched)
    ops._operations[("tests", "req_digest")] = operation
    with pytest.raises(GenerateOperationIntegrityError):
        ops.complete_generate(
            caller_scope="tests",
            request_id="req_digest",
            request_digest=digest,
            lease_owner="owner",
            candidate=mismatched,
        )


def test_generate_ops_rejects_key_identity_mismatch(load_fixture):
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    ops._operations[("tests", "req_key")] = CandidateGenerationOperationV1(
        caller_scope="other-scope",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_key",
        request_digest="sha256:" + ("c" * 64),
        candidate_id="cand_key",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="owner",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(GenerateOperationIntegrityError):
        ops.get_generate_operation("tests", "req_key")


def test_generate_ops_completed_without_expiry_fails_closed(load_fixture):
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    # Bypass model validator to simulate a malformed durable record.
    ops._operations[("tests", "req_malformed")] = (
        CandidateGenerationOperationV1.model_construct(
            caller_scope="tests",
            operation=GENERATE_CANDIDATE_OPERATION,
            request_id="req_malformed",
            request_digest="sha256:" + ("d" * 64),
            candidate_id="cand_malformed",
            status=CandidateGenerationStatusV1.completed,
            lease_owner="owner",
            lease_expires_at=now + timedelta(seconds=60),
            attempt_count=1,
            created_at=now,
            updated_at=now,
            completed_at=now,
            failure=None,
            candidate_expires_at=None,
        )
    )
    with pytest.raises(GenerateOperationIntegrityError):
        ops.get_generate_operation("tests", "req_malformed")
    with pytest.raises(ValueError, match="candidate_expires_at"):
        CandidateGenerationOperationV1(
            caller_scope="tests",
            operation=GENERATE_CANDIDATE_OPERATION,
            request_id="req_malformed",
            request_digest="sha256:" + ("d" * 64),
            candidate_id="cand_malformed",
            status=CandidateGenerationStatusV1.completed,
            lease_owner="owner",
            lease_expires_at=now + timedelta(seconds=60),
            attempt_count=1,
            created_at=now,
            updated_at=now,
            completed_at=now,
            candidate_expires_at=None,
        )


def test_generate_operation_model_rejects_impossible_states():
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationFailureSnapshotV1,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    base = dict(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_state",
        request_digest="sha256:" + ("a" * 64),
        candidate_id="cand_state",
        lease_owner="owner",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ValueError, match="failure"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.completed,
            completed_at=now,
            candidate_expires_at=now + timedelta(minutes=5),
            outcome_digest="sha256:" + ("a" * 64),
            failure=CandidateGenerationFailureSnapshotV1(
                kind="provider_refusal", message="nope"
            ),
        )
    with pytest.raises(ValueError, match="outcome_digest"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.completed,
            completed_at=now,
            candidate_expires_at=now + timedelta(minutes=5),
            outcome_digest=None,
        )
    with pytest.raises(ValueError, match="require failure"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.failed,
            completed_at=now,
            failure=None,
        )
    with pytest.raises(ValueError, match="candidate_expires_at"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.failed,
            completed_at=now,
            failure=CandidateGenerationFailureSnapshotV1(
                kind="provider_refusal", message="nope"
            ),
            candidate_expires_at=now + timedelta(minutes=5),
        )
    with pytest.raises(ValueError, match="outcome_digest"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.failed,
            completed_at=now,
            failure=CandidateGenerationFailureSnapshotV1(
                kind="provider_refusal", message="nope"
            ),
            outcome_digest="sha256:" + ("a" * 64),
        )
    with pytest.raises(ValueError, match="completed_at"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.pending,
            completed_at=now,
        )
    with pytest.raises(ValueError, match="candidate_expires_at"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.pending,
            candidate_expires_at=now + timedelta(minutes=5),
        )
    with pytest.raises(ValueError, match="outcome_digest"):
        CandidateGenerationOperationV1(
            **base,
            status=CandidateGenerationStatusV1.pending,
            outcome_digest="sha256:" + ("a" * 64),
        )


def test_generate_ops_begin_rejects_pending_with_existing_candidate(
    load_fixture,
):
    """Pending + existing candidate is an impossible atomic state; fail closed."""
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import CandidateGenerationStatusV1
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_pending_existing",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    claimed = ops.begin_generate(
        caller_scope="tests",
        request_id="req_pending_existing",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_pending1",
        lease_owner="owner-a",
        lease_duration_seconds=60,
    )
    assert isinstance(claimed, GenerateBeginClaimed)
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    owned = GeneratedStatblockCandidateV1(
        candidate_id="cand_pending1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt={
            "request_id": "req_pending_existing",
            "provider": "test",
            "model": "test-model",
            "prompt_version": "v1",
            "schema_version": "v1",
            "schema_fingerprint": "fp",
            "generated_at": now,
            "caller_scope": "tests",
            "request_digest": digest,
        },
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(owned)
    with pytest.raises(GenerateOperationIntegrityError):
        ops.begin_generate(
            caller_scope="tests",
            request_id="req_pending_existing",
            request_digest=digest,
            candidate_id_factory=lambda: "cand_should_not_use",
            lease_owner="owner-b",
            lease_duration_seconds=60,
        )
    stored = ops.get_generate_operation("tests", "req_pending_existing")
    assert stored is not None
    assert stored.status is CandidateGenerationStatusV1.pending
    assert stored.completed_at is None
    assert candidates._get_unlocked("cand_pending1", now=now, enforce_expiry=False) is not None


def test_generate_ops_complete_rejects_first_write_ownership_mismatch(load_fixture):
    """First persistence must validate receipt binding before creating a candidate."""
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import compute_generate_candidate_digest
    from statblocks_v1.domain.candidate_operations import CandidateGenerationStatusV1
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_first_own",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_first_own",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_first1",
        lease_owner="owner-a",
        lease_duration_seconds=60,
    )
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    base = dict(
        candidate_id="cand_first1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    cases = [
        {
            "request_id": "req_wrong",
            "caller_scope": "tests",
            "request_digest": digest,
        },
        {
            "request_id": "req_first_own",
            "caller_scope": "other-scope",
            "request_digest": digest,
        },
        {
            "request_id": "req_first_own",
            "caller_scope": "tests",
            "request_digest": "sha256:" + ("b" * 64),
        },
        {
            "request_id": "req_first_own",
            "caller_scope": "tests",
            "request_digest": None,
        },
    ]
    for receipt_fields in cases:
        malformed = GeneratedStatblockCandidateV1(
            **base,
            generation_receipt={
                "request_id": receipt_fields["request_id"],
                "provider": "test",
                "model": "test-model",
                "prompt_version": "v1",
                "schema_version": "v1",
                "schema_fingerprint": "fp",
                "generated_at": now,
                "caller_scope": receipt_fields["caller_scope"],
                **(
                    {"request_digest": receipt_fields["request_digest"]}
                    if receipt_fields["request_digest"] is not None
                    else {}
                ),
            },
        )
        with pytest.raises(GenerateOperationIntegrityError):
            ops.complete_generate(
                caller_scope="tests",
                request_id="req_first_own",
                request_digest=digest,
                lease_owner="owner-a",
                candidate=malformed,
            )
        assert "cand_first1" not in candidates._candidates
        pending = ops.get_generate_operation("tests", "req_first_own")
        assert pending is not None
        assert pending.status is CandidateGenerationStatusV1.pending


def test_generate_ops_replay_rejects_altered_mechanics_same_receipt(load_fixture):
    """Same receipt metadata with altered definition must fail outcome binding."""
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import (
        compute_candidate_outcome_digest,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_outcome",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_outcome",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_outcome",
        lease_owner="owner-a",
        lease_duration_seconds=60,
    )
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    original = GeneratedStatblockCandidateV1(
        candidate_id="cand_outcome",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt={
            "request_id": "req_outcome",
            "provider": "test",
            "model": "test-model",
            "prompt_version": "v1",
            "schema_version": "v1",
            "schema_fingerprint": "fp",
            "generated_at": now,
            "caller_scope": "tests",
            "request_digest": digest,
        },
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    completed = ops.complete_generate(
        caller_scope="tests",
        request_id="req_outcome",
        request_digest=digest,
        lease_owner="owner-a",
        candidate=original,
    )
    assert completed.already_completed is False
    stored_op = ops.get_generate_operation("tests", "req_outcome")
    assert stored_op is not None
    assert stored_op.outcome_digest == compute_candidate_outcome_digest(original)

    altered_definition = definition.model_copy(
        update={"identity": definition.identity.model_copy(update={"name": "Altered"})}
    )
    altered = original.model_copy(
        update={
            "definition": altered_definition,
            "validation_receipt": validate_definition(
                altered_definition, ValidationMode.generation_candidate
            ),
        }
    )
    candidates._candidates["cand_outcome"] = altered
    with pytest.raises(GenerateOperationIntegrityError):
        ops.complete_generate(
            caller_scope="tests",
            request_id="req_outcome",
            request_digest=digest,
            lease_owner="owner-a",
            candidate=altered,
        )


def test_generate_ops_begin_rejects_pending_with_foreign_candidate(load_fixture):
    from datetime import datetime, timedelta, timezone

    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import compute_generate_candidate_digest
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = GenerateStatblockCommandV1(
        request_id="req_pending_foreign",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )
    digest = compute_generate_candidate_digest(command)
    ops.begin_generate(
        caller_scope="tests",
        request_id="req_pending_foreign",
        request_digest=digest,
        candidate_id_factory=lambda: "cand_pending2",
        lease_owner="owner-a",
        lease_duration_seconds=60,
    )
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    foreign = GeneratedStatblockCandidateV1(
        candidate_id="cand_pending2",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt={
            "request_id": "req_other",
            "provider": "test",
            "model": "test-model",
            "prompt_version": "v1",
            "schema_version": "v1",
            "schema_fingerprint": "fp",
            "generated_at": now,
            "caller_scope": "tests",
            "request_digest": "sha256:" + ("b" * 64),
        },
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(foreign)
    with pytest.raises(GenerateOperationIntegrityError):
        ops.begin_generate(
            caller_scope="tests",
            request_id="req_pending_foreign",
            request_digest=digest,
            candidate_id_factory=lambda: "cand_x",
            lease_owner="owner-b",
            lease_duration_seconds=60,
        )
