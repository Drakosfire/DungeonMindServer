"""Offline contract smoke; add --live and credentials to target a deployed server."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "Docs/Design/fixtures/dungeonbuddy-statblock-v1/simple_bruiser.json"
PREFIX = "/api/internal/dungeonbuddy/v1"
BUDDY_UI = ROOT.parent / "DungeonMindBuddy" / "apps" / "live-control-ui"
BUDDY_CONTRACT_TEST = (
    "src/contracts/dungeonbuddy-statblocks-v1/dungeonbuddyStatblockV1Contract.test.ts"
)


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _payload(request_id: str) -> dict[str, object]:
    return {
        "request_id": request_id,
        "ruleset": {"system": "dnd5e", "edition": "2024"},
        "source": {
            "name_hint": "Smoke Brute",
            "description": "Disposable offline smoke creature.",
        },
    }


def run_dungeonbuddy_contract_proof() -> None:
    """Require the coordinated DungeonBuddy consumer compile/parse/projection proof.

    Merge order: land DungeonBuddy consumer proof on main before relying on this
    smoke against a sibling checkout (see RUNBOOK merge-order section).
    """
    if not BUDDY_UI.is_dir():
        raise SystemExit(f"DungeonBuddy live-control-ui missing at {BUDDY_UI}")
    contract_test = BUDDY_UI / BUDDY_CONTRACT_TEST
    if not contract_test.is_file():
        raise SystemExit(
            f"DungeonBuddy consumer proof missing at {contract_test}. "
            "Merge DungeonMindBuddy PR #377 (or successor) to main before Server PR20 smoke."
        )
    completed = subprocess.run(
        ["npm", "test", "--", BUDDY_CONTRACT_TEST],
        cwd=BUDDY_UI,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stdout + completed.stderr)


def exercise(client: TestClient, headers: dict[str, str]) -> None:
    request_id = _unique("smoke-generate")
    candidate = client.post(
        f"{PREFIX}/statblock-candidates:generate",
        json=_payload(request_id),
        headers=headers,
    )
    candidate.raise_for_status()
    candidate_body = candidate.json()
    candidate_id = candidate_body["candidate_id"]
    definition = candidate_body["definition"]
    first_digest = candidate_body["validation_receipt"]["definition_digest"]

    read = client.get(f"{PREFIX}/statblock-candidates/{candidate_id}", headers=headers)
    read.raise_for_status()
    assert read.json()["candidate_id"] == candidate_id

    validate = client.post(
        f"{PREFIX}/statblock-definitions:validate",
        headers=headers,
        json={"definition": definition},
    )
    validate.raise_for_status()
    assert validate.json()["definition_digest"] == first_digest

    create = client.post(
        f"{PREFIX}/statblocks",
        headers=headers,
        json={
            "idempotency_key": _unique("smoke-create"),
            "definition": definition,
            "change_summary": "Offline smoke acceptance.",
            "candidate_id": candidate_id,
        },
    )
    create.raise_for_status()
    first = create.json()["revision"]
    statblock_id, first_id = first["statblock_id"], first["revision_id"]
    assert first["definition_digest"] == first_digest

    exact = client.get(
        f"{PREFIX}/statblocks/{statblock_id}/revisions/{first_id}",
        headers=headers,
    )
    exact.raise_for_status()
    assert exact.json()["definition_digest"] == first_digest

    append = client.post(
        f"{PREFIX}/statblocks/{statblock_id}/revisions",
        headers=headers,
        json={
            "idempotency_key": _unique("smoke-append"),
            "parent_revision_id": first_id,
            "definition": definition,
            "change_summary": "Offline smoke append.",
        },
    )
    append.raise_for_status()
    second = append.json()
    assert second["definition_digest"] == first_digest
    assert second["revision_id"] != first_id

    listed = client.get(f"{PREFIX}/statblocks/{statblock_id}/revisions", headers=headers)
    listed.raise_for_status()
    revision_ids = {item["revision_id"] for item in listed.json()["revisions"]}
    assert {first_id, second["revision_id"]} <= revision_ids

    reread_first = client.get(
        f"{PREFIX}/statblocks/{statblock_id}/revisions/{first_id}",
        headers=headers,
    )
    reread_first.raise_for_status()
    assert reread_first.json()["definition_digest"] == first_digest
    assert reread_first.json()["revision_id"] == first_id

    print(
        "smoke passed:",
        statblock_id,
        first_id,
        second["revision_id"],
        definition["identity"]["name"],
    )


def offline(*, run_buddy_proof: bool = True) -> None:
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

    if run_buddy_proof:
        run_dungeonbuddy_contract_proof()

    key, now = "offline-smoke-key", datetime(2026, 1, 1, tzinfo=timezone.utc)
    os.environ.update(
        {
            "DUNGEONBUDDY_INTERNAL_API_KEY": key,
            "OPENAI_API_KEY": "offline-fake",
            "STATBLOCKS_V1_FEATURE_ENABLED": "true",
            "STATBLOCKS_V1_FIRESTORE_ENABLED": "true",
        }
    )
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: now, id_factory=DeterministicIdFactory()
    )
    counter = {"n": 0}

    def next_id() -> str:
        counter["n"] += 1
        return f"cand_smoke{counter['n']}"

    app = create_test_app()
    app.dependency_overrides[get_candidate_repository] = lambda: candidates
    app.dependency_overrides[get_persistence_repository] = lambda: persistence
    app.dependency_overrides[get_clock] = lambda: (lambda: now)
    app.dependency_overrides[get_generation_service] = lambda: GenerationServiceV1(
        provider=FakeDefinitionProvider(json.loads(FIXTURE.read_text())),
        candidates=candidates,
        settings=GenerationSettingsV1("offline", 1.0, 0, 60),
        clock=lambda: now,
        candidate_id_factory=next_id,
    )
    app.dependency_overrides[get_revision_service] = lambda: RevisionServiceV1(
        persistence=persistence, candidates=candidates, clock=lambda: now
    )
    exercise(TestClient(app), {"X-DungeonBuddy-Internal-Key": key})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url")
    parser.add_argument(
        "--live", action="store_true", help="Permit network calls to --base-url."
    )
    parser.add_argument(
        "--skip-buddy-proof",
        action="store_true",
        help="Skip the DungeonBuddy vitest contract consumer proof.",
    )
    args = parser.parse_args()
    if args.base_url and not args.live:
        parser.error("--base-url requires --live to prevent accidental production writes")
    run_buddy_proof = not args.skip_buddy_proof
    if not args.base_url:
        offline(run_buddy_proof=run_buddy_proof)
        return
    key = os.getenv("DUNGEONBUDDY_INTERNAL_API_KEY")
    if not key:
        parser.error("DUNGEONBUDDY_INTERNAL_API_KEY is required for --live")
    if run_buddy_proof:
        run_dungeonbuddy_contract_proof()
    import httpx

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        exercise(client, {"X-DungeonBuddy-Internal-Key": key})  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
