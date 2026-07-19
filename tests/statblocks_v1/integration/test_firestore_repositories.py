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
    AssetWarningCode,
    AssetWarningV1,
    ExactRevisionLocatorV1,
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition
from statblocks_v1.infrastructure.firestore_repositories import (
    CANDIDATES_COLLECTION,
    IDEMPOTENCY_COLLECTION,
    STATBLOCKS_COLLECTION,
    FirestoreCandidateRepository,
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
    assert (CANDIDATES_COLLECTION, STATBLOCKS_COLLECTION, IDEMPOTENCY_COLLECTION) == (
        "dungeonbuddy_statblock_candidates_v1",
        "dungeonbuddy_statblocks_v1",
        "dungeonbuddy_statblock_idempotency_v1",
    )


def test_dump_preserves_native_timestamps_for_ttl_fields(bruiser):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = created + timedelta(hours=1)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id="cand_ttl001",
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


def test_firestore_candidate_ttl_timestamp_round_trip(firestore_client, bruiser):
    repository = FirestoreCandidateRepository(firestore_client)
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expires = created + timedelta(hours=2)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id=f"cand_fs{uuid.uuid4().hex[:10]}",
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
        asset_brief={
            "prompt": "Emulator round-trip creature",
            "recommended_roles": ["portrait", "token"],
        },
        assets=[{"role": "portrait", "url": "https://example.test/portrait.png"}],
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
