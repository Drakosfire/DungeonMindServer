from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from statblocks_v1.api.dependencies import (
    get_candidate_repository,
    get_clock,
    get_generation_service,
)
from statblocks_v1.api.http_errors import register_error_handlers
from statblocks_v1.api.router import router as v1_router
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.provider import ProviderOutcomeKind, ProviderOutcomeV1
from statblocks_v1.application.repositories import CreateStatblockCommand
from statblocks_v1.application.resolvers import PersistenceDefinitionResolver
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.errors import PersistenceUnavailableError, RevisionNotFoundError
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import (
    DeterministicIdFactory,
    InMemoryCandidateGenerationOperationRepository,
    InMemoryCandidateRepository,
    InMemoryStatblockPersistenceRepository,
)
from statblocks_v1.infrastructure.runtime import build_generation_service
from statblocks_v1.testing import create_test_app


@pytest.fixture
def api_client(monkeypatch, load_fixture, auth_headers):
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers["X-DungeonBuddy-Internal-Key"])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: now, id_factory=DeterministicIdFactory()
    )
    counter = {"n": 0}

    def next_candidate_id() -> str:
        counter["n"] += 1
        return f"cand_{counter['n']}"

    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=next_candidate_id,
        definition_resolver=PersistenceDefinitionResolver(persistence),
        generate_operations=InMemoryCandidateGenerationOperationRepository(
            candidates, clock=lambda: now
        ),
        generate_lease_seconds=120,
    )
    app = create_test_app()
    app.dependency_overrides[get_generation_service] = lambda: service
    app.dependency_overrides[get_candidate_repository] = lambda: candidates
    app.dependency_overrides[get_clock] = lambda: (lambda: now)
    return TestClient(app), provider, auth_headers, persistence, candidates, now


def _generate_payload(request_id: str = "request-1") -> dict:
    return {
        "request_id": request_id,
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "source": {"name_hint": "Bruiser", "description": "A reliable test creature."},
    }


def test_generate_and_exact_read(api_client) -> None:
    client, provider, headers, *_ = api_client

    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload(),
        headers=headers,
    )
    second = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("request-2"),
        headers=headers,
    )
    read = client.get("/api/internal/dungeonbuddy/v1/statblock-candidates/cand_1", headers=headers)

    assert first.status_code == 200
    assert first.json()["candidate_id"] == "cand_1"
    assert first.json() == read.json()
    # Distinct request IDs remain independent and each invoke the provider once.
    assert second.status_code == 200
    assert second.json()["candidate_id"] == "cand_2"
    assert len(provider.calls) == 2
    assert "combat_defaults" not in first.text
    assert "markdown" not in first.text.lower()
    assert first.json()["generation_receipt"]["caller_scope"] == "dungeonbuddy"


def test_generate_replay_lost_response_and_conflict(api_client, caplog) -> None:
    import logging

    client, provider, headers, *_ = api_client

    with caplog.at_level(logging.INFO):
        first = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
            json=_generate_payload("req_live_replay_1"),
            headers=headers,
        )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    assert len(provider.calls) == 1
    assert any("candidate_persisted" in message for message in caplog.messages)

    caplog.clear()
    with caplog.at_level(logging.INFO):
        replay = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
            json=_generate_payload("req_live_replay_1"),
            headers=headers,
        )
    assert replay.status_code == 200
    assert replay.json()["candidate_id"] == candidate_id
    assert replay.json() == first.json()
    assert len(provider.calls) == 1
    assert any("candidate_generate_replay" in message for message in caplog.messages)
    assert any("idempotency_replay" in message for message in caplog.messages)
    assert not any("candidate_persisted" in message for message in caplog.messages)

    conflict_payload = _generate_payload("req_live_replay_1")
    conflict_payload["source"]["description"] = "A different creature description."
    conflict = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=conflict_payload,
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert len(provider.calls) == 1


def test_generate_premature_candidate_loss_returns_500(api_client) -> None:
    client, provider, headers, _, candidates, _ = api_client
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("premature-loss"),
        headers=headers,
    )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    del candidates._candidates[candidate_id]
    replay = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("premature-loss"),
        headers=headers,
    )
    assert replay.status_code == 500
    assert replay.json()["error"]["code"] == "candidate_missing_before_expiry"
    assert replay.json()["error"]["details"]["candidate_id"] == candidate_id
    assert len(provider.calls) == 1


def test_generate_terminal_failure_replay(api_client, load_fixture) -> None:
    client, provider, headers, *_ = api_client
    provider._outcome = ProviderOutcomeV1(kind=ProviderOutcomeKind.timeout, message="slow")

    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("fail-key"),
        headers=headers,
    )
    second = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("fail-key"),
        headers=headers,
    )
    assert first.status_code == 504
    assert second.status_code == 504
    assert first.json()["error"]["code"] == second.json()["error"]["code"] == "provider_timeout"
    assert len(provider.calls) == 1


def test_generate_expired_candidate_replay_410(api_client) -> None:
    client, provider, headers, _, candidates, now = api_client
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("expire-key"),
        headers=headers,
    )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    # Force expiry on stored candidate while keeping operation completed.
    stored = candidates.get_for_acceptance(candidate_id)
    candidates._candidates[candidate_id] = stored.model_copy(
        update={"expires_at": now}
    )
    replay = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("expire-key"),
        headers=headers,
    )
    assert replay.status_code == 410
    assert replay.json()["error"]["code"] == "candidate_expired"
    assert replay.json()["error"]["details"]["candidate_id"] == candidate_id
    assert len(provider.calls) == 1


def test_candidate_read_reports_missing_and_expired(api_client) -> None:
    client, _, headers, _, _, _ = api_client

    missing = client.get(
        "/api/internal/dungeonbuddy/v1/statblock-candidates/cand_missing", headers=headers
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "candidate_not_found"

    generated = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload(),
        headers=headers,
    )
    assert generated.status_code == 200
    expired_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    client.app.dependency_overrides[get_clock] = lambda: (lambda: expired_at)

    expired = client.get("/api/internal/dungeonbuddy/v1/statblock-candidates/cand_1", headers=headers)
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "candidate_expired"


def test_candidate_routes_require_internal_auth(api_client) -> None:
    client, _, headers, *_ = api_client
    path = "/api/internal/dungeonbuddy/v1/statblock-candidates:generate"

    missing = client.post(path, json=_generate_payload())
    wrong = client.post(
        path, json=_generate_payload(), headers={**headers, "X-DungeonBuddy-Internal-Key": "wrong"}
    )

    assert missing.status_code == 401
    assert wrong.status_code == 403
    assert missing.json()["error"]["code"] == wrong.json()["error"]["code"] == (
        "unauthorized_internal_client"
    )


@pytest.mark.parametrize(
    ("outcome", "status", "code"),
    [
        (ProviderOutcomeV1(ProviderOutcomeKind.refusal), 422, "provider_refused"),
        (ProviderOutcomeV1(ProviderOutcomeKind.incomplete), 422, "provider_incomplete"),
        (ProviderOutcomeV1(ProviderOutcomeKind.timeout), 504, "provider_timeout"),
        (ProviderOutcomeV1(ProviderOutcomeKind.rate_limit), 429, "rate_limited"),
        (ProviderOutcomeV1(ProviderOutcomeKind.failure), 503, "provider_unavailable"),
        (ProviderOutcomeV1.succeeded({"not": "a definition"}), 422, "validation_failed"),
    ],
)
def test_generation_failures_use_typed_envelopes(api_client, outcome, status, code) -> None:
    client, _, headers, *_ = api_client
    provider = FakeDefinitionProvider(outcome)
    candidates = InMemoryCandidateRepository()
    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        candidate_id_factory=lambda: "cand_2",
    )

    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload(),
        headers=headers,
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_ruleset_and_source_digest_mismatches_are_not_provider_unavailable(
    api_client, load_fixture
) -> None:
    client, _, headers, *_ = api_client
    payload = dict(load_fixture("simple_bruiser"))
    payload["ruleset"] = {"system": "dnd5e", "edition": "2014", "house_ruleset_id": None}
    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider(payload),
        candidates=InMemoryCandidateRepository(),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        candidate_id_factory=lambda: "cand_ruleset",
    )

    ruleset = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload(),
        headers=headers,
    )
    assert ruleset.status_code == 422
    assert ruleset.json()["error"]["code"] == "ruleset_mismatch"

    digest_payload = _generate_payload()
    digest_payload["source"]["description_digest"] = "sha256:" + ("0" * 64)
    digest = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=digest_payload,
        headers=headers,
    )
    assert digest.status_code == 422
    assert digest.json()["error"]["code"] == "source_digest_mismatch"


def test_revise_from_definition_and_exact_locator(api_client, load_fixture) -> None:
    client, _, headers, persistence, *_ = api_client
    definition = load_fixture("simple_bruiser")

    inline = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json={
            "request_id": "revise-inline",
            "ruleset": {"system": "dnd5e", "edition": "2024"},
            "revision_instructions": ["Keep the club."],
            "source_definition": definition,
        },
        headers=headers,
    )
    assert inline.status_code == 200
    assert inline.json()["generation_receipt"]["source_definition_digest"].startswith("sha256:")
    assert inline.json()["generation_receipt"]["source_locator"] is None

    created_statblock, created_revision = persistence.create_statblock(
        CreateStatblockCommand(
            caller_scope="tests",
            idempotency_key="revise-source",
            definition=StatblockDefinitionV1.model_validate(definition),
            created_by="tests",
        )
    )
    locator = {
        "statblock_id": created_statblock.statblock_id,
        "revision_id": created_revision.revision_id,
    }
    located = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json={
            "request_id": "revise-locate",
            "ruleset": {"system": "dnd5e", "edition": "2024"},
            "revision_instructions": ["Tighten the club."],
            "source_locator": locator,
        },
        headers=headers,
    )
    assert located.status_code == 200
    assert located.json()["source_locator"] == locator
    assert located.json()["generation_receipt"]["source_locator"] == locator
    assert (
        located.json()["generation_receipt"]["source_definition_digest"]
        == created_revision.definition_digest
    )


def test_revise_invalid_source_combinations_are_422(api_client, load_fixture) -> None:
    client, _, headers, *_ = api_client
    definition = load_fixture("simple_bruiser")
    base = {
        "request_id": "revise-invalid",
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "revision_instructions": ["noop"],
    }

    neither = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json=base,
        headers=headers,
    )
    both = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json={
            **base,
            "source_definition": definition,
            "source_locator": {"statblock_id": "sb_1", "revision_id": "rev_1"},
        },
        headers=headers,
    )

    assert neither.status_code == both.status_code == 422
    assert neither.json()["error"]["code"] == both.json()["error"]["code"] == "invalid_request"
    assert "fields" in neither.json()["error"]["details"]


def test_revise_missing_revision_is_typed_404(api_client) -> None:
    client, _, headers, *_ = api_client

    class MissingResolver:
        def resolve(self, locator):
            raise RevisionNotFoundError(locator.revision_id)

    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider({}),
        candidates=InMemoryCandidateRepository(),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        definition_resolver=MissingResolver(),
    )
    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json={
            "request_id": "revise-missing",
            "ruleset": {"system": "dnd5e", "edition": "2024"},
            "revision_instructions": ["noop"],
            "source_locator": {"statblock_id": "sb_missing01", "revision_id": "rev_missing01"},
        },
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "revision_not_found"


def test_revise_persistence_unavailable_is_typed_503(api_client) -> None:
    client, _, headers, *_ = api_client

    class UnavailableResolver:
        def resolve(self, locator):
            raise PersistenceUnavailableError()

    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider({}),
        candidates=InMemoryCandidateRepository(),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        definition_resolver=UnavailableResolver(),
    )
    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json={
            "request_id": "revise-persistence-down",
            "ruleset": {"system": "dnd5e", "edition": "2024"},
            "revision_instructions": ["noop"],
            "source_locator": {"statblock_id": "sb_persist01", "revision_id": "rev_persist01"},
        },
        headers=headers,
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "persistence_unavailable"


def test_validate_and_openapi_models(api_client, load_fixture) -> None:
    client, _, headers, *_ = api_client
    definition = load_fixture("simple_bruiser")

    validate_response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-definitions:validate",
        json={"definition": definition},
        headers=headers,
    )
    invalid_validation = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-definitions:validate",
        json={"definition": load_fixture("dangling_multiattack_ref")},
        headers=headers,
    )
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    generate = paths["/api/internal/dungeonbuddy/v1/statblock-candidates:generate"]["post"]
    revise = paths["/api/internal/dungeonbuddy/v1/statblock-candidates:revise"]["post"]
    components = schema["components"]["schemas"]

    assert validate_response.status_code == 200
    assert validate_response.json()["definition_digest"].startswith("sha256:")
    assert invalid_validation.status_code == 200
    assert invalid_validation.json()["validation_receipt"]["status"] == "invalid"
    assert "ErrorEnvelopeV1" in components
    assert "GeneratedStatblockCandidateV1" in components
    assert "422" in generate["responses"]
    assert "409" in generate["responses"]
    assert "410" in generate["responses"]
    assert "500" in generate["responses"]
    assert "503" in generate["responses"]
    assert "404" in paths["/api/internal/dungeonbuddy/v1/statblock-candidates/{candidate_id}"]["get"][
        "responses"
    ]
    assert "404" in revise["responses"]
    assert "422" in revise["responses"]
    assert "500" in revise["responses"]
    assert "503" in revise["responses"]


class _LegacyEchoBody(BaseModel):
    name: str


def test_legacy_routes_keep_fastapi_validation_envelope(monkeypatch) -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(v1_router)
    # Endpoint Depends may resolve before body validation; keep service configured
    # so this test isolates envelope shape rather than missing-factory 503s.
    app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider({}),
        candidates=InMemoryCandidateRepository(),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
    )

    @app.post("/legacy/echo")
    async def legacy_echo(body: _LegacyEchoBody) -> dict:
        return {"name": body.name}

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "legacy-isolation-key")
    client = TestClient(app)

    legacy = client.post("/legacy/echo", json={})
    v1 = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json={},
        headers={"X-DungeonBuddy-Internal-Key": "legacy-isolation-key"},
    )

    assert legacy.status_code == 422
    assert "detail" in legacy.json()
    assert "error" not in legacy.json()
    assert v1.status_code == 422
    assert set(v1.json().keys()) == {"error"}
    assert v1.json()["error"]["code"] == "invalid_request"
    assert "fields" in v1.json()["error"]["details"]


def test_production_generation_service_wires_persistence_resolver(monkeypatch) -> None:
    class DummyProvider:
        provider_name = "dummy"

        def generate_definition(self, **kwargs):
            raise AssertionError("not called")

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("STATBLOCKS_V1_OPENAI_MODEL", "test-model")
    candidates = InMemoryCandidateRepository()
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        id_factory=DeterministicIdFactory(),
    )
    service = build_generation_service(
        candidates=candidates,
        persistence=persistence,
        provider=DummyProvider(),
    )
    assert isinstance(service._definition_resolver, PersistenceDefinitionResolver)
    assert service._definition_resolver._repository is persistence
