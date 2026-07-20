"""Offline contract smoke; add --live and credentials to target a deployed server."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "Docs/Design/fixtures/dungeonbuddy-statblock-v1/simple_bruiser.json"


def _payload() -> dict[str, object]:
    return {
        "request_id": "smoke-generate-1",
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "source": {
            "name_hint": "Smoke Brute",
            "description": "Disposable offline smoke creature.",
        },
    }


def _exercise(client: TestClient, headers: dict[str, str]) -> None:
    candidate = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        json=_payload(),
        headers=headers,
    )
    candidate.raise_for_status()
    definition = candidate.json()["definition"]
    create = client.post(
        "/api/internal/dungeonbuddy/v1/statblocks",
        headers=headers,
        json={
            "idempotency_key": "smoke-create-1",
            "definition": definition,
            "change_summary": "Offline smoke acceptance.",
        },
    )
    create.raise_for_status()
    first = create.json()["revision"]
    statblock_id, first_id = first["statblock_id"], first["revision_id"]
    exact = client.get(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{first_id}",
        headers=headers,
    )
    exact.raise_for_status()
    assert exact.json()["definition_digest"] == first["definition_digest"]
    append = client.post(
        f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions",
        headers=headers,
        json={
            "idempotency_key": "smoke-append-1",
            "parent_revision_id": first_id,
            "definition": definition,
            "change_summary": "Offline smoke append.",
        },
    )
    append.raise_for_status()
    assert (
        client.get(
            f"/api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{first_id}",
            headers=headers,
        ).json()
        == first
    )
    print(f"smoke passed: {statblock_id} {first_id} {append.json()['revision_id']}")


def _offline() -> None:
    from statblocks_v1.api.dependencies import (
        get_candidate_repository,
        get_clock,
        get_generation_service,
        get_persistence_repository,
        get_revision_service,
    )
    from statblocks_v1.application.generation import GenerationServiceV1
    from statblocks_v1.application.revisions import RevisionServiceV1
    from statblocks_v1.application.settings import GenerationSettingsV1
    from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
    from statblocks_v1.infrastructure.memory_repositories import (
        DeterministicIdFactory,
        InMemoryCandidateRepository,
        InMemoryStatblockPersistenceRepository,
    )
    from statblocks_v1.testing import create_test_app

    key, now = "offline-smoke-key", datetime(2026, 1, 1, tzinfo=timezone.utc)
    os.environ.update(
        {
            "DUNGEONBUDDY_INTERNAL_API_KEY": key,
            "OPENAI_API_KEY": "offline-fake",
        }
    )
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: now, id_factory=DeterministicIdFactory()
    )
    app = create_test_app()
    app.dependency_overrides[get_candidate_repository] = lambda: candidates
    app.dependency_overrides[get_persistence_repository] = lambda: persistence
    app.dependency_overrides[get_clock] = lambda: (lambda: now)
    app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider(json.loads(FIXTURE.read_text())),
        candidates=candidates,
        settings=GenerationSettingsV1("offline", 1.0, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_smoke1",
    )
    app.dependency_overrides[get_revision_service] = lambda: RevisionServiceV1(
        persistence=persistence, candidates=candidates, clock=lambda: now
    )
    _exercise(TestClient(app), {"X-DungeonBuddy-Internal-Key": key})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument(
        "--live", action="store_true", help="Permit network calls to --base-url."
    )
    args = parser.parse_args()
    if args.base_url and not args.live:
        parser.error("--base-url requires --live to prevent accidental production writes")
    if not args.base_url:
        _offline()
        return
    key = os.getenv("DUNGEONBUDDY_INTERNAL_API_KEY")
    if not key:
        parser.error("DUNGEONBUDDY_INTERNAL_API_KEY is required for --live")
    import httpx

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        _exercise(client, {"X-DungeonBuddy-Internal-Key": key})  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
