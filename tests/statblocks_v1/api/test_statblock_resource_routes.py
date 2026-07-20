"""HTTP acceptance routes for durable logical-statblock revisions (PR18)."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import (
    get_candidate_repository,
    get_clock,
    get_persistence_repository,
    get_revision_service,
)
from statblocks_v1.application.revisions import SERVICE_CREATED_BY, RevisionServiceV1
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition
from statblocks_v1.infrastructure.memory_repositories import (
    DeterministicIdFactory,
    InMemoryCandidateRepository,
    InMemoryStatblockPersistenceRepository,
)
from statblocks_v1.testing import create_test_app


@pytest.fixture
def resource_client(monkeypatch, load_fixture, auth_headers):
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers["X-DungeonBuddy-Internal-Key"])
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: now, id_factory=DeterministicIdFactory()
    )
    service = RevisionServiceV1(
        persistence=persistence, candidates=candidates, clock=lambda: now
    )
    app = create_test_app()
    app.dependency_overrides[get_candidate_repository] = lambda: candidates
    app.dependency_overrides[get_persistence_repository] = lambda: persistence
    app.dependency_overrides[get_revision_service] = lambda: service
    app.dependency_overrides[get_clock] = lambda: (lambda: now)
    return TestClient(app), load_fixture("simple_bruiser"), candidates, persistence, now, auth_headers


def _create_payload(definition: dict, key: str = "create-1", **extra) -> dict:
    payload = {
        "idempotency_key": key,
        "definition": definition,
        "change_summary": "Accepted after DungeonBuddy review.",
        "actor": "user_123",
        "accepted_through": {"surface": "review_panel"},
        "asset_bindings": [{"asset_id": "asset_123", "role": "portrait"}],
    }
    payload.update(extra)
    return payload


def _store_candidate(candidates, definition: dict, now: datetime, *, candidate_id: str = "cand_000001", expired: bool = False):
    model = StatblockDefinitionV1.model_validate(definition)
    candidate = GeneratedStatblockCandidateV1(
        candidate_id=candidate_id,
        definition=model,
        validation_receipt=validate_definition(
            model, ValidationMode.generation_candidate, validated_at=now
        ),
        created_at=now,
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(hours=1),
    )
    candidates.create(candidate)
    return candidate


def test_create_append_and_exact_replay(resource_client) -> None:
    client, definition, _, _, _, headers = resource_client
    created = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(definition),
        headers=headers,
    )
    assert created.status_code == 200
    first = created.json()
    assert first["statblock"]["created_by"] == SERVICE_CREATED_BY
    assert first["revision"]["provenance"]["accepted_by"] == "user_123"
    assert "candidate" not in first["revision"]["provenance"]
    statblock_id = first["statblock"]["statblock_id"]
    first_revision_id = first["revision"]["revision_id"]

    replay = client.get(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{first_revision_id}",
        headers=headers,
    )
    assert replay.status_code == 200
    for field in (
        "definition",
        "canonical_definition",
        "definition_digest",
        "validation_receipt",
        "provenance",
        "asset_bindings",
    ):
        assert replay.json()[field] == first["revision"][field]

    appended = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "append-1"),
            "parent_revision_id": first_revision_id,
        },
        headers=headers,
    )
    assert appended.status_code == 200
    second = appended.json()
    assert client.get(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{first_revision_id}",
        headers=headers,
    ).json() == first["revision"]

    logical = client.get(f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}", headers=headers)
    listed = client.get(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions", headers=headers
    )
    assert logical.json()["latest_revision_id"] == second["revision_id"]
    assert [revision["revision_id"] for revision in listed.json()["revisions"]] == [
        first_revision_id,
        second["revision_id"],
    ]

    create_replay = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(definition),
        headers=headers,
    )
    assert create_replay.status_code == 200
    assert create_replay.json()["revision"] == first["revision"]

    append_replay = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "append-1"),
            "parent_revision_id": first_revision_id,
        },
        headers=headers,
    )
    assert append_replay.status_code == 200
    assert append_replay.json() == second


def test_write_idempotency_parent_stale_and_exact_locator_errors(resource_client) -> None:
    client, definition, _, _, _, headers = resource_client
    created = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(definition),
        headers=headers,
    )
    statblock_id = created.json()["statblock"]["statblock_id"]
    revision_id = created.json()["revision"]["revision_id"]

    changed_request = _create_payload(definition)
    changed_request["change_summary"] = "A changed acceptance decision."
    conflict = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=changed_request,
        headers=headers,
    )
    wrong_parent = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={**_create_payload(definition, "append-1"), "parent_revision_id": "rev_999999"},
        headers=headers,
    )
    append = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "append-ok"),
            "parent_revision_id": revision_id,
        },
        headers=headers,
    )
    stale_parent = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "append-stale"),
            "parent_revision_id": revision_id,
        },
        headers=headers,
    )
    append_conflict = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "append-ok"),
            "change_summary": "Changed append acceptance.",
            "parent_revision_id": revision_id,
        },
        headers=headers,
    )
    wrong_pair = client.get(
        f"/api/internal/dungeonbuddy/v1/statblocks/sb_999999/revisions/{revision_id}",
        headers=headers,
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    assert wrong_parent.status_code == 409
    assert wrong_parent.json()["error"]["code"] == "parent_revision_mismatch"
    assert append.status_code == 200
    assert stale_parent.status_code == 409
    assert stale_parent.json()["error"]["code"] == "stale_parent_revision"
    assert append_conflict.status_code == 409
    assert append_conflict.json()["error"]["code"] == "idempotency_conflict"
    assert wrong_pair.status_code == 404


def test_candidate_linked_edit_and_replay_after_ttl_deletion(resource_client) -> None:
    client, definition, candidates, _, now, headers = resource_client
    _store_candidate(candidates, definition, now, expired=True)

    edited = copy.deepcopy(definition)
    edited["identity"]["name"] = "Edited Bruiser"

    accepted = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(edited, candidate_id="cand_000001"),
        headers=headers,
    )
    assert accepted.status_code == 200
    first = accepted.json()
    assert first["statblock"]["created_by"] == SERVICE_CREATED_BY
    provenance = first["revision"]["provenance"]["candidate"]
    assert provenance["candidate_id"] == "cand_000001"
    assert provenance["accepted_definition_changed"] is True

    candidate_read = client.get(
        "/api/internal/dungeonbuddy/v1/statblock-candidates/cand_000001", headers=headers
    )
    assert candidate_read.status_code == 410

    with candidates._lock:
        del candidates._candidates["cand_000001"]

    missing = client.get(
        "/api/internal/dungeonbuddy/v1/statblock-candidates/cand_000001", headers=headers
    )
    assert missing.status_code == 404

    replay = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(edited, candidate_id="cand_000001"),
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json()["revision"] == first["revision"]


def test_open_provenance_field_rejected_and_actor_is_not_created_by(resource_client) -> None:
    client, definition, _, _, _, headers = resource_client
    spoofed = _create_payload(definition)
    spoofed["provenance"] = {
        "candidate": {
            "candidate_id": "cand_forged",
            "accepted_definition_changed": False,
        }
    }
    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks", json=spoofed, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"

    created = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(definition, actor="spoofed_owner"),
        headers=headers,
    )
    assert created.status_code == 200
    body = created.json()
    assert body["statblock"]["created_by"] == SERVICE_CREATED_BY
    assert body["revision"]["provenance"]["accepted_by"] == "spoofed_owner"


def test_persistence_validation_failure_returns_receipt(resource_client, load_fixture) -> None:
    client, _, _, _, _, headers = resource_client
    invalid = load_fixture("unknown_resource_pool")
    response = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(invalid),
        headers=headers,
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_failed"
    assert "validation_receipt" in error["details"]
    assert error["details"]["is_persistence_ready"] is False
    assert error["details"]["validation_receipt"]["mode"] == "persistence"
    assert error["details"]["validation_receipt"]["status"] == "invalid"


def test_idempotency_conflict_before_validation_for_changed_invalid_payload(
    resource_client, load_fixture
) -> None:
    """Same key + changed invalid definition must 409, never 422 validation_failed."""

    client, definition, _, _, _, headers = resource_client
    invalid = load_fixture("unknown_resource_pool")

    created = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(definition, "order-create"),
        headers=headers,
    )
    assert created.status_code == 200
    first = created.json()
    statblock_id = first["statblock"]["statblock_id"]
    revision_id = first["revision"]["revision_id"]

    create_conflict = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        json=_create_payload(invalid, "order-create"),
        headers=headers,
    )
    assert create_conflict.status_code == 409
    assert create_conflict.json()["error"]["code"] == "idempotency_conflict"

    append = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(definition, "order-append"),
            "parent_revision_id": revision_id,
        },
        headers=headers,
    )
    assert append.status_code == 200

    append_conflict = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        json={
            **_create_payload(invalid, "order-append"),
            "parent_revision_id": revision_id,
        },
        headers=headers,
    )
    assert append_conflict.status_code == 409
    assert append_conflict.json()["error"]["code"] == "idempotency_conflict"


def test_concurrent_same_key_create_and_competing_appends(resource_client) -> None:
    client, definition, _, _, _, headers = resource_client

    def create_once():
        return client.post(
            "/api/internal/dungeonbuddy/v1/statblocks",
            json=_create_payload(definition, "concurrent-create"),
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        create_results = list(pool.map(lambda _: create_once(), range(8)))
    assert {result.status_code for result in create_results} == {200}
    create_bodies = [result.json() for result in create_results]
    assert len({body["revision"]["revision_id"] for body in create_bodies}) == 1
    assert all(body == create_bodies[0] for body in create_bodies)

    statblock_id = create_bodies[0]["statblock"]["statblock_id"]
    parent = create_bodies[0]["revision"]["revision_id"]

    def append_once(key: str):
        return client.post(
            f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
            json={
                **_create_payload(definition, key),
                "parent_revision_id": parent,
            },
            headers=headers,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(append_once, "append-a")
        second = pool.submit(append_once, "append-b")
        outcomes = [first.result(), second.result()]

    statuses = sorted(result.status_code for result in outcomes)
    assert statuses == [200, 409]
    success = next(result for result in outcomes if result.status_code == 200)
    conflict = next(result for result in outcomes if result.status_code == 409)
    assert conflict.json()["error"]["code"] == "stale_parent_revision"
    assert (
        client.get(
            f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}", headers=headers
        ).json()["latest_revision_id"]
        == success.json()["revision_id"]
    )


def test_openapi_resource_errors_and_no_mutation_routes(resource_client) -> None:
    client, _, _, _, _, _ = resource_client
    schema = client.app.openapi()
    paths = schema["paths"]

    create = paths["/api/internal/dungeonbuddy/v1/statblocks"]["post"]
    append = paths["/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions"]["post"]
    exact = paths[
        "/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{revision_id}"
    ]["get"]

    for operation in (create, append):
        assert "409" in operation["responses"]
        assert "422" in operation["responses"]
        assert "404" in operation["responses"]
        assert "503" in operation["responses"]
    assert "404" in exact["responses"]

    revision_collection = paths["/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions"]
    revision_item = paths[
        "/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{revision_id}"
    ]
    assert set(revision_collection) <= {"get", "post"}
    assert set(revision_item) == {"get"}
    for method in ("put", "patch", "delete"):
        assert method not in revision_collection
        assert method not in revision_item
