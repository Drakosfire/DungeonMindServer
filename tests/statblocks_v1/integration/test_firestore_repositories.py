"""Firestore emulator coverage; skipped unless FIRESTORE_EMULATOR_HOST is set."""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from statblocks_v1.application.repositories import AppendRevisionCommand, CreateStatblockCommand
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import StaleParentRevisionError, StatblockNotFoundError
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    STATBLOCK_CONTRACT,
    STATBLOCK_CONTRACT_VERSION,
    AssetWarningCode,
    AssetWarningV1,
    ExactRevisionLocatorV1,
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
)
from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition
from statblocks_v1.infrastructure.firestore_repositories import (
    CANDIDATES_COLLECTION,
    GENERATE_OPS_COLLECTION,
    IDEMPOTENCY_COLLECTION,
    REVISE_OPS_COLLECTION,
    STATBLOCKS_COLLECTION,
    FirestoreCandidateGenerationOperationRepository,
    FirestoreCandidateRepository,
    FirestoreCandidateRevisionOperationRepository,
    FirestoreStatblockPersistenceRepository,
    _dump,
)

pytestmark = pytest.mark.firestore_emulator


@pytest.fixture
def firestore_client():
    if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        pytest.skip("Firestore emulator is not configured")
    from google.cloud import firestore

    return firestore.Client(
        project=os.environ.get("GOOGLE_CLOUD_PROJECT", "statblocks-v1-test")
    )


@pytest.fixture
def bruiser(load_fixture):
    return StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))


def test_v1_collection_layout_is_isolated():
    assert (
        CANDIDATES_COLLECTION,
        STATBLOCKS_COLLECTION,
        IDEMPOTENCY_COLLECTION,
        GENERATE_OPS_COLLECTION,
        REVISE_OPS_COLLECTION,
    ) == (
        "dungeonbuddy_statblock_candidates_v1",
        "dungeonbuddy_statblocks_v1",
        "dungeonbuddy_statblock_idempotency_v1",
        "dungeonbuddy_statblock_candidate_generate_ops_v1",
        "dungeonbuddy_statblock_candidate_revise_ops_v1",
    )


def test_dump_preserves_native_timestamps_for_ttl_fields(bruiser):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = created + timedelta(hours=1)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_ttl001",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(bruiser, ValidationMode.generation_candidate),
        created_at=created,
        expires_at=expires,
    )
    dumped = _dump(candidate)
    assert isinstance(dumped["expires_at"], datetime)
    assert isinstance(dumped["created_at"], datetime)
    assert dumped["expires_at"] == expires


def test_firestore_create_round_trip_and_create_replay(firestore_client, bruiser):
    repository = FirestoreStatblockPersistenceRepository(firestore_client)
    command = CreateStatblockCommand(
        caller_scope="dungeonbuddy",
        idempotency_key="fs-create-1",
        definition=bruiser,
        created_by="dungeonbuddy",
    )
    statblock, first = repository.create_statblock(command)
    repository.append_revision(
        AppendRevisionCommand(
            caller_scope="dungeonbuddy",
            idempotency_key="fs-append-1",
            statblock_id=statblock.statblock_id,
            parent_revision_id=first.revision_id,
            definition=bruiser,
        )
    )
    replay_statblock, replay_revision = repository.create_statblock(command)
    assert replay_revision.revision_id == first.revision_id
    assert replay_statblock.statblock_id == statblock.statblock_id

    loaded = repository.get_revision(statblock.statblock_id, first.revision_id)
    assert loaded.canonical_definition == first.canonical_definition
    assert loaded.definition_digest == first.definition_digest


def test_firestore_restart_replay_returns_identical_revision(firestore_client, bruiser):
    """Recreate the repository instance to prove durable idempotency survives process restart."""
    key = f"fs-restart-{uuid.uuid4().hex[:8]}"
    first_repo = FirestoreStatblockPersistenceRepository(firestore_client)
    command = CreateStatblockCommand(
        caller_scope="dungeonbuddy",
        idempotency_key=key,
        definition=bruiser,
        created_by="dungeonbuddy",
        provenance={"change_summary": "restart proof"},
    )
    _, first = first_repo.create_statblock(command)

    restarted = FirestoreStatblockPersistenceRepository(firestore_client)
    _, replay = restarted.create_statblock(command)
    exact = restarted.get_revision(first.statblock_id, first.revision_id)
    assert replay.model_dump(mode="json") == first.model_dump(mode="json")
    assert exact.model_dump(mode="json") == first.model_dump(mode="json")


def test_firestore_candidate_ttl_timestamp_round_trip(firestore_client, bruiser):
    repository = FirestoreCandidateRepository(firestore_client)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = created + timedelta(hours=2)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id=f"cand_fs{uuid.uuid4().hex[:10]}",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(bruiser, ValidationMode.generation_candidate),
        created_at=created,
        expires_at=expires,
    )
    repository.create(candidate)
    snapshot = (
        firestore_client.collection(CANDIDATES_COLLECTION)
        .document(candidate.candidate_id)
        .get()
    )
    raw = snapshot.to_dict()
    assert isinstance(raw["expires_at"], datetime)
    loaded = repository.get(candidate.candidate_id, now=created)
    assert loaded.expires_at == expires


def test_firestore_candidate_typed_contract_round_trip(firestore_client, bruiser):
    repository = FirestoreCandidateRepository(firestore_client)
    created = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
    expires = created + timedelta(hours=6)
    locator = ExactRevisionLocatorV1(statblock_id="sb_fsource01", revision_id="rev_fsource01")
    source_definition_digest = compute_definition_digest(bruiser)
    candidate_id = f"cand_fs{uuid.uuid4().hex[:10]}"
    candidate = GeneratedStatblockCandidateV1(
        candidate_id=candidate_id,
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(
            bruiser, ValidationMode.generation_candidate, validated_at=created
        ),
        generation_receipt=GenerationReceiptV1(
            request_id="req_fs_typed",
            provider="fake",
            model="test-model",
            prompt_version="statblock-generation-prompt-v1",
            schema_version="statblock-openai-schema-v1",
            schema_fingerprint="fp_test",
            generated_at=created,
            caller_scope="dungeonbuddy",
            actor="emulator",
            source_description_digest="sha256:" + ("a" * 64),
            source_definition_digest=source_definition_digest,
            source_locator=locator,
            latency_ms=0,
        ),
        asset_brief=AssetBriefV1(
            prompt="Emulator round-trip creature",
            recommended_roles=["portrait", "token"],
        ),
        assets=[
            AssetRefV1(
                asset_id="asset_emulator_portrait",
                provider_kind="cloudflare_images",
                url="https://example.test/portrait.png",
                mime_type="image/png",
                created_at=created,
            )
        ],
        asset_warnings=[
            AssetWarningV1(
                code=AssetWarningCode.asset_generator_unconfigured,
                message="Asset generation was requested but no asset generator is configured.",
            ),
            AssetWarningV1(
                code=AssetWarningCode.asset_generation_failed,
                message="Asset generation failed; review the candidate without assets.",
            ),
        ],
        created_at=created,
        expires_at=expires,
        source_locator=locator,
    )

    repository.create(candidate)
    raw = (
        firestore_client.collection(CANDIDATES_COLLECTION)
        .document(candidate_id)
        .get()
        .to_dict()
    )
    assert isinstance(raw["expires_at"], datetime)
    assert isinstance(raw["created_at"], datetime)
    assert isinstance(raw["generation_receipt"]["generated_at"], datetime)
    assert raw["generation_receipt"]["source_definition_digest"] == source_definition_digest
    assert raw["generation_receipt"]["source_locator"] == {
        "statblock_id": "sb_fsource01",
        "revision_id": "rev_fsource01",
    }
    assert raw["asset_warnings"] == [
        {
            "code": "asset_generator_unconfigured",
            "message": "Asset generation was requested but no asset generator is configured.",
        },
        {
            "code": "asset_generation_failed",
            "message": "Asset generation failed; review the candidate without assets.",
        },
    ]
    assert raw["asset_brief"]["prompt"] == "Emulator round-trip creature"

    loaded = repository.get(candidate_id, now=created)
    assert loaded.model_dump(mode="json") == candidate.model_dump(mode="json")
    assert loaded.generation_receipt is not None
    assert loaded.generation_receipt.source_definition_digest == source_definition_digest
    assert loaded.generation_receipt.source_locator == locator
    assert loaded.source_locator == locator
    assert [warning.code for warning in loaded.asset_warnings] == [
        AssetWarningCode.asset_generator_unconfigured,
        AssetWarningCode.asset_generation_failed,
    ]
    assert loaded.asset_brief == candidate.asset_brief


def test_firestore_concurrent_append_only_one_succeeds(firestore_client, bruiser):
    repository = FirestoreStatblockPersistenceRepository(firestore_client)
    statblock, first = repository.create_statblock(
        CreateStatblockCommand(
            caller_scope="dungeonbuddy",
            idempotency_key="fs-create-concurrent",
            definition=bruiser,
            created_by="dungeonbuddy",
        )
    )

    def attempt(key: str):
        return repository.append_revision(
            AppendRevisionCommand(
                caller_scope="dungeonbuddy",
                idempotency_key=key,
                statblock_id=statblock.statblock_id,
                parent_revision_id=first.revision_id,
                definition=bruiser,
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt, "fs-append-a"), pool.submit(attempt, "fs-append-b")]
        results = []
        errors = []
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:  # noqa: BLE001 - assert typed stale-parent below
                errors.append(error)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], StaleParentRevisionError)
    assert repository.get(statblock.statblock_id).latest_revision_id == results[0].revision_id
    assert len(repository.list_for_statblock(statblock.statblock_id)) == 2


def test_firestore_missing_statblock_is_not_parent_mismatch(firestore_client, bruiser):
    repository = FirestoreStatblockPersistenceRepository(firestore_client)
    with pytest.raises(StatblockNotFoundError):
        repository.append_revision(
            AppendRevisionCommand(
                caller_scope="dungeonbuddy",
                idempotency_key="fs-missing-sb",
                statblock_id="sb_doesnotexist01",
                parent_revision_id="rev_doesnotexist01",
                definition=bruiser,
            )
        )


def test_firestore_generate_ops_atomic_complete_and_replay(firestore_client, bruiser):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        GenerateBeginCompleted,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.errors import IdempotencyConflictError
    from statblocks_v1.domain.profiles import RulesetRef

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    candidates = FirestoreCandidateRepository(firestore_client, clock=lambda: now)
    ops = FirestoreCandidateGenerationOperationRepository(
        firestore_client,
        clock=lambda: now,
        candidates_collection=CANDIDATES_COLLECTION,
        generate_ops_collection=GENERATE_OPS_COLLECTION,
    )
    command = GenerateStatblockCommandV1(
        request_id=f"fs-gen-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="X", description="Y"),
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy"),
    )
    digest = compute_generate_candidate_digest(command)
    candidate_id = f"cand_fsgen{suffix}"

    claimed = ops.begin_generate(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: candidate_id,
        lease_owner="owner-a",
        lease_duration_seconds=120,
    )
    assert isinstance(claimed, GenerateBeginClaimed)
    assert claimed.operation.candidate_id == candidate_id

    with pytest.raises(IdempotencyConflictError):
        ops.begin_generate(
            caller_scope="dungeonbuddy",
            request_id=command.request_id,
            request_digest=compute_generate_candidate_digest(
                command.model_copy(
                    update={"source": SourceSnapshotV1(name_hint="X", description="changed")}
                )
            ),
            candidate_id_factory=lambda: f"cand_other{suffix}",
            lease_owner="owner-b",
            lease_duration_seconds=120,
        )

    candidate = GeneratedStatblockCandidateV1(
        candidate_id=candidate_id,
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(bruiser, ValidationMode.generation_candidate),
        generation_receipt=GenerationReceiptV1(
            request_id=command.request_id,
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="dungeonbuddy",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    stored = ops.complete_generate(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        lease_owner="owner-a",
        candidate=candidate,
    )
    assert stored.candidate.candidate_id == candidate_id
    assert stored.already_completed is False
    assert candidates.get(candidate_id, now=now).candidate_id == candidate_id

    # Restart-style replay via new repository instances.
    ops2 = FirestoreCandidateGenerationOperationRepository(firestore_client, clock=lambda: now)
    began = ops2.begin_generate(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: f"cand_new{suffix}",
        lease_owner="owner-c",
        lease_duration_seconds=120,
    )
    assert isinstance(began, GenerateBeginCompleted)
    assert began.candidate_id == candidate_id

    # Concurrent complete converges on one document.
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                ops.complete_generate,
                caller_scope="dungeonbuddy",
                request_id=command.request_id,
                request_digest=digest,
                lease_owner="stale",
                candidate=candidate,
            )
            for _ in range(2)
        ]
        results = [future.result() for future in futures]
    assert {item.candidate.candidate_id for item in results} == {candidate_id}
    assert all(item.already_completed for item in results)


def test_firestore_revise_ops_atomic_complete_and_replay(firestore_client, bruiser):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        ReviseStatblockCommandV1,
    )
    from statblocks_v1.application.repositories import (
        ReviseBeginClaimed,
        ReviseBeginCompleted,
        compute_revise_candidate_digest,
    )
    from statblocks_v1.domain.errors import IdempotencyConflictError
    from statblocks_v1.domain.profiles import RulesetRef

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    candidates = FirestoreCandidateRepository(firestore_client, clock=lambda: now)
    ops = FirestoreCandidateRevisionOperationRepository(
        firestore_client,
        clock=lambda: now,
        candidates_collection=CANDIDATES_COLLECTION,
        revise_ops_collection=REVISE_OPS_COLLECTION,
    )
    command = ReviseStatblockCommandV1(
        request_id=f"fs-rev-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Adjust for Firestore revise ops"],
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy"),
        source_definition=bruiser,
    )
    digest = compute_revise_candidate_digest(command)
    candidate_id = f"cand_fsrev{suffix}"

    claimed = ops.begin_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: candidate_id,
        lease_owner="owner-a",
        lease_duration_seconds=120,
    )
    assert isinstance(claimed, ReviseBeginClaimed)
    assert claimed.operation.candidate_id == candidate_id

    with pytest.raises(IdempotencyConflictError):
        ops.begin_revise(
            caller_scope="dungeonbuddy",
            request_id=command.request_id,
            request_digest=compute_revise_candidate_digest(
                command.model_copy(update={"revision_instructions": ["Changed instructions"]})
            ),
            candidate_id_factory=lambda: f"cand_other{suffix}",
            lease_owner="owner-b",
            lease_duration_seconds=120,
        )

    candidate = GeneratedStatblockCandidateV1(
        candidate_id=candidate_id,
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(bruiser, ValidationMode.generation_candidate),
        generation_receipt=GenerationReceiptV1(
            request_id=command.request_id,
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="dungeonbuddy",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    stored = ops.complete_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        lease_owner="owner-a",
        candidate=candidate,
    )
    assert stored.candidate.candidate_id == candidate_id
    assert stored.already_completed is False
    assert candidates.get(candidate_id, now=now).candidate_id == candidate_id

    ops2 = FirestoreCandidateRevisionOperationRepository(
        firestore_client, clock=lambda: now
    )
    began = ops2.begin_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: f"cand_new{suffix}",
        lease_owner="owner-c",
        lease_duration_seconds=120,
    )
    assert isinstance(began, ReviseBeginCompleted)
    assert began.operation.candidate_id == candidate_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                ops.complete_revise,
                caller_scope="dungeonbuddy",
                request_id=command.request_id,
                request_digest=digest,
                lease_owner="stale",
                candidate=candidate,
            )
            for _ in range(2)
        ]
        results = [future.result() for future in futures]
    assert {item.candidate.candidate_id for item in results} == {candidate_id}
    assert all(item.already_completed for item in results)


def test_firestore_revise_ops_concurrent_first_claims_reserve_one_candidate_id(
    firestore_client, bruiser
):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        ReviseStatblockCommandV1,
    )
    from statblocks_v1.application.repositories import (
        ReviseBeginClaimed,
        ReviseBeginInProgress,
        compute_revise_candidate_digest,
    )
    from statblocks_v1.domain.profiles import RulesetRef

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    ops = FirestoreCandidateRevisionOperationRepository(
        firestore_client,
        clock=lambda: now,
        candidates_collection=CANDIDATES_COLLECTION,
        revise_ops_collection=REVISE_OPS_COLLECTION,
    )
    command = ReviseStatblockCommandV1(
        request_id=f"fs-rev-race-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Race to claim revise lease"],
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy"),
        source_definition=bruiser,
    )
    digest = compute_revise_candidate_digest(command)

    def attempt(owner: str):
        return ops.begin_revise(
            caller_scope="dungeonbuddy",
            request_id=command.request_id,
            request_digest=digest,
            candidate_id_factory=lambda: f"cand_unused{owner}{suffix}",
            lease_owner=owner,
            lease_duration_seconds=120,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, ["a", "b", "c", "d"]))

    claimed = [item for item in results if isinstance(item, ReviseBeginClaimed)]
    in_progress = [item for item in results if isinstance(item, ReviseBeginInProgress)]
    assert len(claimed) == 1
    reserved_id = claimed[0].operation.candidate_id
    assert all(item.operation.candidate_id == reserved_id for item in claimed)
    assert all(item.candidate_id == reserved_id for item in in_progress)


def test_firestore_revise_ops_expired_lease_takeover_retains_reserved_candidate_id(
    firestore_client, bruiser
):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        ReviseStatblockCommandV1,
    )
    from statblocks_v1.application.repositories import (
        ReviseBeginClaimed,
        compute_revise_candidate_digest,
    )
    from statblocks_v1.domain.profiles import RulesetRef

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    suffix = uuid.uuid4().hex[:8]
    ops = FirestoreCandidateRevisionOperationRepository(
        firestore_client,
        clock=lambda: now["t"],
        candidates_collection=CANDIDATES_COLLECTION,
        revise_ops_collection=REVISE_OPS_COLLECTION,
    )
    command = ReviseStatblockCommandV1(
        request_id=f"fs-rev-takeover-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Hold the revise lease"],
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy"),
        source_definition=bruiser,
    )
    digest = compute_revise_candidate_digest(command)
    reserved = f"cand_fsvrtake{suffix}"

    claimed = ops.begin_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: reserved,
        lease_owner="owner-a",
        lease_duration_seconds=30,
    )
    assert isinstance(claimed, ReviseBeginClaimed)
    assert claimed.operation.candidate_id == reserved

    now["t"] = now["t"] + timedelta(seconds=31)
    takeover = ops.begin_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: f"cand_shouldnot{suffix}",
        lease_owner="owner-b",
        lease_duration_seconds=30,
    )
    assert isinstance(takeover, ReviseBeginClaimed)
    assert takeover.operation.candidate_id == reserved
    assert takeover.operation.attempt_count == 2


def test_firestore_revise_ops_indeterminate_complete_reconciles(firestore_client, bruiser):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        ReviseStatblockCommandV1,
    )
    from statblocks_v1.application.repositories import (
        ReviseBeginClaimed,
        compute_revise_candidate_digest,
    )
    from statblocks_v1.domain.profiles import RulesetRef

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    ops = FirestoreCandidateRevisionOperationRepository(
        firestore_client,
        clock=lambda: now,
        candidates_collection=CANDIDATES_COLLECTION,
        revise_ops_collection=REVISE_OPS_COLLECTION,
    )
    command = ReviseStatblockCommandV1(
        request_id=f"fs-rev-reconcile-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Complete once then stale-worker replay"],
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy"),
        source_definition=bruiser,
    )
    digest = compute_revise_candidate_digest(command)
    candidate_id = f"cand_fsrecon{suffix}"

    claimed = ops.begin_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        candidate_id_factory=lambda: candidate_id,
        lease_owner="owner-a",
        lease_duration_seconds=120,
    )
    assert isinstance(claimed, ReviseBeginClaimed)

    candidate = GeneratedStatblockCandidateV1(
        candidate_id=candidate_id,
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=bruiser,
        validation_receipt=validate_definition(bruiser, ValidationMode.generation_candidate),
        generation_receipt=GenerationReceiptV1(
            request_id=command.request_id,
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="dungeonbuddy",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    stored = ops.complete_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        lease_owner="owner-a",
        candidate=candidate,
    )
    assert stored.already_completed is False

    stale_payload = candidate.model_copy(update={"asset_brief": None})
    again = ops.complete_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        lease_owner="owner-stale",
        candidate=stale_payload,
    )
    assert again.candidate.candidate_id == candidate_id
    assert again.already_completed is True
    assert again.candidate.model_dump(mode="json") == stored.candidate.model_dump(mode="json")

    # Simulated post-commit transport uncertainty: transaction() raises before the
    # transactional body runs; reconcile must still return the completed candidate.
    def _boom_transaction():
        raise RuntimeError("simulated indeterminate commit")

    ops._client.transaction = _boom_transaction  # type: ignore[method-assign]
    reconciled = ops.complete_revise(
        caller_scope="dungeonbuddy",
        request_id=command.request_id,
        request_digest=digest,
        lease_owner="owner-stale",
        candidate=stale_payload,
    )
    assert reconciled.candidate.candidate_id == candidate_id
    assert reconciled.already_completed is True


def test_firestore_revise_replay_through_fresh_generation_service(
    firestore_client, bruiser, load_fixture
):
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        ReviseStatblockCommandV1,
    )
    from statblocks_v1.application.generation import GenerateOutcomeV1, GenerationServiceV1
    from statblocks_v1.application.settings import GenerationSettingsV1
    from statblocks_v1.domain.profiles import RulesetRef
    from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    suffix = uuid.uuid4().hex[:8]
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    command = ReviseStatblockCommandV1(
        request_id=f"fs-rev-svc-{suffix}",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Service-level Firestore replay proof"],
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy", actor="emulator"),
        source_definition=bruiser,
    )
    fixed_candidate_id = f"cand_fssvc{suffix}"

    def build_service() -> GenerationServiceV1:
        candidates = FirestoreCandidateRepository(firestore_client, clock=lambda: now)
        revise_ops = FirestoreCandidateRevisionOperationRepository(
            firestore_client,
            clock=lambda: now,
            candidates_collection=CANDIDATES_COLLECTION,
            revise_ops_collection=REVISE_OPS_COLLECTION,
        )
        generate_ops = FirestoreCandidateGenerationOperationRepository(
            firestore_client,
            clock=lambda: now,
            candidates_collection=CANDIDATES_COLLECTION,
            generate_ops_collection=GENERATE_OPS_COLLECTION,
        )
        return GenerationServiceV1(
            provider=provider,
            candidates=candidates,
            settings=GenerationSettingsV1("test-model", 1, 0, 3600),
            clock=lambda: now,
            candidate_id_factory=lambda: fixed_candidate_id,
            generate_operations=generate_ops,
            revise_operations=revise_ops,
        )

    first = build_service().revise(command)
    second = build_service().revise(command)

    assert isinstance(first, GenerateOutcomeV1)
    assert isinstance(second, GenerateOutcomeV1)
    assert first.replayed is False
    assert second.replayed is True
    assert first.candidate_id == second.candidate_id == fixed_candidate_id
    assert len(provider.calls) == 1
