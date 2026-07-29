from __future__ import annotations

import copy
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
from statblocks_v1.application.generation import (
    GenerationFailureV1,
    GenerationServiceV1,
)
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
    InMemoryCandidateRevisionOperationRepository,
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
        revise_operations=InMemoryCandidateRevisionOperationRepository(
            candidates, clock=lambda: now
        ),
        generate_lease_seconds=120,
        revise_lease_seconds=120,
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
    assert first.json()["generation_receipt"]["request_digest"].startswith("sha256:")


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


def test_revise_replay_lost_response_and_conflict(api_client, load_fixture, caplog) -> None:
    import logging

    client, provider, headers, *_ = api_client
    source = load_fixture("simple_bruiser")
    payload = {
        "request_id": "req_revise_replay_1",
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "revision_instructions": ["Make it scarier"],
        "source_definition": source,
    }

    with caplog.at_level(logging.INFO):
        first = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
            json=payload,
            headers=headers,
        )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    assert first.json()["generation_receipt"]["request_digest"].startswith("sha256:")
    assert len(provider.calls) == 1

    caplog.clear()
    with caplog.at_level(logging.INFO):
        replay = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
            json=payload,
            headers=headers,
        )
    assert replay.status_code == 200
    assert replay.json()["candidate_id"] == candidate_id
    assert len(provider.calls) == 1
    assert any("candidate_revise_replay" in message for message in caplog.messages)
    assert any("idempotency_replay" in message for message in caplog.messages)

    conflict = dict(payload)
    conflict["revision_instructions"] = ["Totally different edit"]
    conflict_response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json=conflict,
        headers=headers,
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "idempotency_conflict"
    assert len(provider.calls) == 1


def test_revise_locator_replay_lost_response_and_conflict(
    api_client, load_fixture, caplog
) -> None:
    import logging

    client, provider, headers, persistence, *_ = api_client
    definition = load_fixture("simple_bruiser")
    created_statblock, created_revision = persistence.create_statblock(
        CreateStatblockCommand(
            caller_scope="tests",
            idempotency_key="revise-locator-replay",
            definition=StatblockDefinitionV1.model_validate(definition),
            created_by="tests",
        )
    )
    locator = {
        "statblock_id": created_statblock.statblock_id,
        "revision_id": created_revision.revision_id,
    }
    payload = {
        "request_id": "req_revise_locator_replay_1",
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "revision_instructions": ["Make it scarier via locator"],
        "source_locator": locator,
    }

    with caplog.at_level(logging.INFO):
        first = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
            json=payload,
            headers=headers,
        )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    assert first.json()["generation_receipt"]["request_digest"].startswith("sha256:")
    assert first.json()["source_locator"] == locator
    assert len(provider.calls) == 1

    caplog.clear()
    with caplog.at_level(logging.INFO):
        replay = client.post(
            "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
            json=payload,
            headers=headers,
        )
    assert replay.status_code == 200
    assert replay.json()["candidate_id"] == candidate_id
    assert replay.json() == first.json()
    assert len(provider.calls) == 1
    assert any("candidate_revise_replay" in message for message in caplog.messages)
    assert any("idempotency_replay" in message for message in caplog.messages)

    conflict = dict(payload)
    conflict["revision_instructions"] = ["Totally different locator edit"]
    conflict_response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json=conflict,
        headers=headers,
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["error"]["code"] == "idempotency_conflict"
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
    from datetime import timedelta

    from statblocks_v1.api.dependencies import get_generation_service
    from statblocks_v1.domain.candidate_operations import CandidateGenerationStatusV1

    client, provider, headers, _, candidates, now = api_client
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("expire-key"),
        headers=headers,
    )
    assert first.status_code == 200
    candidate_id = first.json()["candidate_id"]
    # Durable expiry authority is the operation record, not candidate-document TTL.
    from statblocks_v1.application.repositories import compute_candidate_outcome_digest

    service = client.app.dependency_overrides[get_generation_service]()
    ops = service._generate_operations
    assert ops is not None
    operation = ops._operations[("dungeonbuddy", "expire-key")]
    assert operation.status is CandidateGenerationStatusV1.completed
    past = now - timedelta(seconds=1)
    # Keep op/candidate expiry agreement and outcome_digest aligned so this is
    # ordinary 410 after load+verify, not an integrity mismatch.
    stored = candidates.get_for_acceptance(candidate_id)
    expired_candidate = stored.model_copy(update={"expires_at": past})
    candidates._candidates[candidate_id] = expired_candidate
    ops._operations[("dungeonbuddy", "expire-key")] = operation.model_copy(
        update={
            "candidate_expires_at": past,
            "outcome_digest": compute_candidate_outcome_digest(expired_candidate),
        }
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
        generate_operations=InMemoryCandidateGenerationOperationRepository(candidates),
    )

    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload(),
        headers=headers,
    )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    if code == "validation_failed":
        details = response.json()["error"].get("details")
        assert details is not None
        assert details.get("phase") == "schema_validation"
        assert details.get("issue_count", 0) >= 1
        assert "issues" in details
        assert "__DMS_VAL01_RAW_PAYLOAD_SENTINEL__" not in response.text
        assert '"input":' not in response.text


def test_domain_invalid_generate_and_revise_return_candidates_with_invalid_receipts(
    api_client, load_fixture
) -> None:
    client, _, headers, *_ = api_client
    candidates = InMemoryCandidateRepository()
    invalid_provider = FakeDefinitionProvider(load_fixture("dangling_multiattack_ref"))
    counter = {"n": 0}

    def next_candidate_id() -> str:
        counter["n"] += 1
        return f"cand_{counter['n']}"

    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=invalid_provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        candidate_id_factory=next_candidate_id,
        generate_operations=InMemoryCandidateGenerationOperationRepository(candidates),
        revise_operations=InMemoryCandidateRevisionOperationRepository(candidates),
    )

    generate = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("diag-generate"),
        headers=headers,
    )
    assert generate.status_code == 200
    gen_receipt = generate.json()["validation_receipt"]
    assert gen_receipt["status"] == "invalid"
    gen_codes = {issue["code"] for issue in gen_receipt["issues"]}
    assert "UNKNOWN_MULTIATTACK_ELEMENT" in gen_codes

    revise_payload = {
        "request_id": "diag-revise",
        "ruleset": {"system": "dnd5e", "edition": "2024", "house_ruleset_id": None},
        "revision_instructions": ["Tweak the latchling."],
        "source_definition": load_fixture("dangling_multiattack_ref"),
        "intent": {},
        "context": {},
        "preserve_element_keys": True,
    }
    revise = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
        json=revise_payload,
        headers=headers,
    )
    assert revise.status_code == 200
    rev_receipt = revise.json()["validation_receipt"]
    assert rev_receipt["status"] == "invalid"
    assert len(invalid_provider.calls) == 2


RAW_PROVIDER_KEY_SENTINEL = "__RAW_PROVIDER_KEY_SENTINEL__"


def _payload_with_raw_extra_provider_keys(load_fixture) -> dict:
    payload = copy.deepcopy(load_fixture("simple_bruiser"))
    payload[RAW_PROVIDER_KEY_SENTINEL] = "x"
    payload["rule_elements"][0][RAW_PROVIDER_KEY_SENTINEL] = "y"
    return payload


def test_extra_forbidden_provider_key_sentinel_absent_from_generate_http_and_replay(
    api_client, load_fixture
) -> None:
    client, provider, headers, *_ = api_client
    provider._outcome = ProviderOutcomeV1.succeeded(
        _payload_with_raw_extra_provider_keys(load_fixture)
    )
    payload = _generate_payload("raw-key-http")
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    second = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 422
    assert second.status_code == 422
    assert RAW_PROVIDER_KEY_SENTINEL not in first.text
    assert RAW_PROVIDER_KEY_SENTINEL not in second.text
    details = first.json()["error"]["details"]
    extra_paths = {
        issue["field_path"]
        for issue in details["issues"]
        if issue["code"] == "EXTRA_FORBIDDEN"
    }
    assert "<unexpected_key>" in extra_paths
    assert "rule_elements[0].<unexpected_key>" in extra_paths
    assert len(provider.calls) == 1


RAW_PROVIDER_VALUE_SENTINEL = "__RAW_PROVIDER_VALUE_SENTINEL__"
RAW_DOMAIN_VALUE_SENTINEL = "__RAW_DOMAIN_VALUE_SENTINEL__"


def test_domain_invalid_generate_returns_candidate_and_replays_without_provider(
    api_client, load_fixture
) -> None:
    client, provider, headers, *_ = api_client
    outcome_payload = copy.deepcopy(load_fixture("simple_bruiser"))
    sentinel_skill = {
        "skill": RAW_DOMAIN_VALUE_SENTINEL,
        "ability": "strength",
        "value": 6,
        "derivation": "standard",
    }
    outcome_payload["proficiencies"]["skills"] = [
        sentinel_skill,
        copy.deepcopy(sentinel_skill),
    ]
    provider._outcome = ProviderOutcomeV1.succeeded(outcome_payload)
    payload = _generate_payload("raw-domain-value-http")
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    second = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_receipt = first.json()["validation_receipt"]
    assert first_receipt["status"] == "invalid"
    dup_issues = [
        issue for issue in first_receipt["issues"] if issue["code"] == "DUPLICATE_SKILL_NAME"
    ]
    assert dup_issues
    # Provider-authored value is editable candidate content, not an error leak.
    assert RAW_DOMAIN_VALUE_SENTINEL in first.text
    assert first.json()["candidate_id"] == second.json()["candidate_id"]
    assert len(provider.calls) == 1


def test_union_tag_invalid_provider_value_sentinel_absent_from_generate_http_and_replay(
    api_client, load_fixture
) -> None:
    client, provider, headers, *_ = api_client
    outcome_payload = copy.deepcopy(load_fixture("simple_bruiser"))
    outcome_payload["rule_elements"][0]["mechanic"]["kind"] = RAW_PROVIDER_VALUE_SENTINEL
    provider._outcome = ProviderOutcomeV1.succeeded(outcome_payload)
    payload = _generate_payload("raw-value-http")
    first = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    second = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=payload,
        headers=headers,
    )
    assert first.status_code == 422
    assert second.status_code == 422
    assert RAW_PROVIDER_VALUE_SENTINEL not in first.text
    assert RAW_PROVIDER_VALUE_SENTINEL not in second.text
    assert len(provider.calls) == 1
    issues = first.json()["error"]["details"]["issues"]
    union_issues = [issue for issue in issues if issue["code"] == "UNION_TAG_INVALID"]
    assert union_issues
    assert RAW_PROVIDER_VALUE_SENTINEL not in union_issues[0]["message"]


def test_misbound_generation_failure_never_exposes_diagnostics_in_http(api_client) -> None:
    from statblocks_v1.domain.candidate_operations import (
        GenerationValidationDiagnosticIssueV1,
        GenerationValidationDiagnosticPacketV1,
        GenerationValidationPhaseV1,
    )
    from statblocks_v1.domain.receipts import ValidationSeverity

    client, _, headers, *_ = api_client
    packet = GenerationValidationDiagnosticPacketV1(
        phase=GenerationValidationPhaseV1.schema_validation,
        issue_count=1,
        issues=[
            GenerationValidationDiagnosticIssueV1(
                code="MISSING",
                severity=ValidationSeverity.error,
                field_path="identity.name",
                message="Field required",
            )
        ],
    )

    class MisboundFailureService:
        def generate(self, command):
            return GenerationFailureV1(
                "unexpected_kind_for_test", "boom", diagnostics=packet
            )

    client.app.dependency_overrides[get_generation_service] = lambda: MisboundFailureService()
    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_generate_payload("misbound-diagnostics"),
        headers=headers,
    )
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "generation_failed"
    assert "details" not in error


def test_ruleset_and_source_digest_mismatches_are_not_provider_unavailable(
    api_client, load_fixture
) -> None:
    client, _, headers, *_ = api_client
    payload = dict(load_fixture("simple_bruiser"))
    payload["ruleset"] = {"system": "dnd5e", "edition": "2014", "house_ruleset_id": None}
    candidates = InMemoryCandidateRepository()
    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider(payload),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        candidate_id_factory=lambda: "cand_ruleset",
        generate_operations=InMemoryCandidateGenerationOperationRepository(candidates),
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
    client, _, headers, _, candidates, now = api_client

    class MissingResolver:
        def resolve(self, locator):
            raise RevisionNotFoundError(locator.revision_id)

    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider({}),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        definition_resolver=MissingResolver(),
        revise_operations=InMemoryCandidateRevisionOperationRepository(
            candidates, clock=lambda: now
        ),
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
    client, _, headers, _, candidates, now = api_client

    class UnavailableResolver:
        def resolve(self, locator):
            raise PersistenceUnavailableError()

    client.app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider({}),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        definition_resolver=UnavailableResolver(),
        revise_operations=InMemoryCandidateRevisionOperationRepository(
            candidates, clock=lambda: now
        ),
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
    assert "409" in revise["responses"]
    assert "410" in revise["responses"]
    assert "idempotency" in revise["responses"].get("409", {}).get("description", "").lower()
    assert "revise-operation" in revise["responses"].get("500", {}).get(
        "description", ""
    ).lower()


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
        generate_operations=InMemoryCandidateGenerationOperationRepository(candidates),
        revise_operations=InMemoryCandidateRevisionOperationRepository(candidates),
        provider=DummyProvider(),
    )
    assert isinstance(service._definition_resolver, PersistenceDefinitionResolver)
    assert service._definition_resolver._repository is persistence
