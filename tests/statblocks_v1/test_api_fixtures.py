from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import (
    get_candidate_repository,
    get_clock,
    get_generation_service,
)
from statblocks_v1.api.models import ErrorEnvelopeV1, ReviseCandidateRequestV1
from statblocks_v1.application.commands import CallerProvenanceV1, ReviseStatblockCommandV1
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.prompts import PROMPT_VERSION
from statblocks_v1.application.repositories import compute_revise_candidate_digest
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import (
    InMemoryCandidateGenerationOperationRepository,
    InMemoryCandidateRevisionOperationRepository,
    InMemoryCandidateRepository,
)
from statblocks_v1.testing import create_test_app

API_FIXTURE_DIRECTORY = (
    Path(__file__).parents[2]
    / "Docs"
    / "Design"
    / "fixtures"
    / "dungeonbuddy-statblock-v1-api"
)

INTERNAL_KEY = "test-statblocks-v1-internal-key"


def _load(name: str) -> dict:
    return json.loads((API_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def _route_command(request: ReviseCandidateRequestV1) -> ReviseStatblockCommandV1:
    """Mirror ``revise_candidate`` router mapping for digest coherence checks."""

    return ReviseStatblockCommandV1(
        request_id=request.request_id,
        ruleset=request.ruleset,
        revision_instructions=request.revision_instructions,
        source_definition=request.source_definition,
        source_locator=request.source_locator,
        source=request.source,
        intent=request.intent,
        context=request.context,
        asset_options=request.asset_options,
        preserve_element_keys=request.preserve_element_keys,
        caller=CallerProvenanceV1(caller_scope="dungeonbuddy", actor=request.actor),
    )


def test_revise_request_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-request.json")
    assert "_note" not in raw
    request = ReviseCandidateRequestV1.model_validate(raw)
    assert request.request_id == "fixture-revise-source-def-1"
    assert request.actor == "fixture"
    assert request.source_definition is not None
    assert request.source_locator is None
    assert request.revision_instructions == ["Tighten melee damage for table pace."]
    assert request.model_dump(mode="json") == raw


def test_revise_replay_response_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-replay-response.json")
    assert "_note" not in raw
    candidate = GeneratedStatblockCandidateV1.model_validate(raw)
    assert candidate.candidate_id == "cand_fix00000001"
    assert candidate.definition is not None
    assert candidate.validation_receipt is not None
    assert candidate.generation_receipt is not None
    assert candidate.generation_receipt.request_id == "fixture-revise-source-def-1"
    assert candidate.generation_receipt.actor == "fixture"
    assert candidate.generation_receipt.request_digest.startswith("sha256:")
    assert candidate.generation_receipt.prompt_version == PROMPT_VERSION
    assert candidate.model_dump(mode="json") == raw


def test_revise_conflict_response_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-conflict-response.json")
    assert "_note" not in raw
    envelope = ErrorEnvelopeV1.model_validate(raw)
    assert envelope.error.code == "idempotency_conflict"
    assert envelope.error.message == "Idempotency key was reused with a different request"
    assert envelope.error.details == {"idempotency_key": "fixture-revise-source-def-1"}
    assert envelope.model_dump(mode="json") == raw


def test_revise_request_and_replay_response_fixtures_are_mutually_coherent() -> None:
    request = ReviseCandidateRequestV1.model_validate(_load("revise-request.json"))
    candidate = GeneratedStatblockCandidateV1.model_validate(_load("revise-replay-response.json"))
    receipt = candidate.generation_receipt
    assert receipt is not None
    assert request.source_definition is not None

    command = _route_command(request)
    assert compute_revise_candidate_digest(command) == receipt.request_digest
    assert request.actor == receipt.actor
    assert request.request_id == receipt.request_id
    assert compute_definition_digest(request.source_definition) == receipt.source_definition_digest


def test_revise_request_fixture_round_trips_through_fastapi_route(monkeypatch) -> None:
    """Prove the HTTP revise route maps ``request.actor`` into the digesting command.

    Compiles the live OpenAI strict schema so local Pydantic drift cannot mask the
    actor/digest coherence assertion this fixture pair exists to document.
    """

    import hashlib

    from statblocks_v1.application import generation as generation_module
    from statblocks_v1.application.schema_compiler import CompiledSchemaV1, SCHEMA_COMPILER_VERSION
    from statblocks_v1.domain.schema import openai_strict_json_schema

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", INTERNAL_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    def _compile_live() -> CompiledSchemaV1:
        schema = openai_strict_json_schema()
        encoded = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
        return CompiledSchemaV1(
            name="statblock_definition_v1",
            schema=schema,
            compiler_version=SCHEMA_COMPILER_VERSION,
            fingerprint=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
        )

    # generation.py binds the compiler name at import time.
    monkeypatch.setattr(
        generation_module, "compile_openai_definition_schema", _compile_live
    )

    request = ReviseCandidateRequestV1.model_validate(_load("revise-request.json"))
    committed = GeneratedStatblockCandidateV1.model_validate(_load("revise-replay-response.json"))
    assert request.source_definition is not None
    assert committed.generation_receipt is not None

    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    provider = FakeDefinitionProvider(request.source_definition.model_dump(mode="json"))
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_fix00000001",
        generate_operations=InMemoryCandidateGenerationOperationRepository(
            candidates, clock=lambda: now
        ),
        revise_operations=InMemoryCandidateRevisionOperationRepository(
            candidates, clock=lambda: now
        ),
    )
    app = create_test_app()
    app.dependency_overrides[get_generation_service] = lambda: service
    app.dependency_overrides[get_candidate_repository] = lambda: candidates
    app.dependency_overrides[get_clock] = lambda: (lambda: now)

    response = TestClient(app).post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json=request.model_dump(mode="json"),
        headers={"X-DungeonBuddy-Internal-Key": INTERNAL_KEY},
    )
    assert response.status_code == 200, response.text
    live = GeneratedStatblockCandidateV1.model_validate(response.json())
    assert live.generation_receipt is not None
    assert live.generation_receipt.request_id == request.request_id
    assert live.generation_receipt.actor == request.actor
    assert live.generation_receipt.request_digest == compute_revise_candidate_digest(
        _route_command(request)
    )
    assert live.generation_receipt.source_definition_digest == compute_definition_digest(
        request.source_definition
    )
    assert live.generation_receipt.request_digest == committed.generation_receipt.request_digest
    assert live.generation_receipt.actor == committed.generation_receipt.actor
    assert live.candidate_id == committed.candidate_id
