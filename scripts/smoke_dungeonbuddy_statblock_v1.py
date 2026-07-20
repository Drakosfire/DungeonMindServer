"""Offline contract smoke; add --live and credentials to target a deployed server."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "Docs/Design/fixtures/dungeonbuddy-statblock-v1/simple_bruiser.json"
HUMAN_FIXTURE = ROOT / "Docs/Design/fixtures/dungeonbuddy-statblock-v1/human_adjudicated.json"
API_FIXTURES = ROOT / "Docs/Design/fixtures/dungeonbuddy-statblock-v1-api"
CLIENT_TS = ROOT / "generated/dungeonbuddy-statblocks-v1/client.ts"
PREFIX = "/api/internal/dungeonbuddy/v1"


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


def compile_generated_client() -> None:
    buddy_tsc = (
        ROOT.parent
        / "DungeonMindBuddy"
        / "apps"
        / "live-control-ui"
        / "node_modules"
        / "typescript"
        / "bin"
        / "tsc"
    )
    tsc = str(buddy_tsc) if buddy_tsc.is_file() else shutil.which("tsc")
    if tsc is None and shutil.which("npx") is None:
        raise SystemExit("tsc or npx is required to compile the generated TypeScript client")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "client.ts").write_text(CLIENT_TS.read_text(encoding="utf-8"), encoding="utf-8")
        (tmp_path / "tsconfig.json").write_text(
            json.dumps(
                {
                    "compilerOptions": {
                        "target": "ES2022",
                        "module": "ESNext",
                        "moduleResolution": "bundler",
                        "strict": True,
                        "noEmit": True,
                        "skipLibCheck": True,
                        "lib": ["ES2022", "DOM"],
                    },
                    "files": ["client.ts"],
                }
            ),
            encoding="utf-8",
        )
        command = (
            [tsc, "--project", "tsconfig.json"]
            if tsc is not None
            else ["npx", "--yes", "-p", "typescript@5.6.3", "tsc", "--project", "tsconfig.json"]
        )
        completed = subprocess.run(
            command,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(completed.stdout + completed.stderr)


def parse_api_fixtures_and_human_adjudicated() -> dict[str, object]:
    from statblocks_v1.api.models import (
        CreateStatblockRequestV1,
        CreateStatblockResponseV1,
        ErrorEnvelopeV1,
        GenerateCandidateRequestV1,
        ValidationResponseV1,
    )
    from statblocks_v1.application.projection import combat_minimums
    from statblocks_v1.domain.resources import (
        GeneratedStatblockCandidateV1,
        StatblockRevisionResourceV1,
    )
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

    GenerateCandidateRequestV1.model_validate_json(
        (API_FIXTURES / "generate-request.json").read_text(encoding="utf-8")
    )
    GeneratedStatblockCandidateV1.model_validate_json(
        (API_FIXTURES / "candidate-response.json").read_text(encoding="utf-8")
    )
    ValidationResponseV1.model_validate_json(
        (API_FIXTURES / "validate-response.json").read_text(encoding="utf-8")
    )
    CreateStatblockRequestV1.model_validate_json(
        (API_FIXTURES / "create-request.json").read_text(encoding="utf-8")
    )
    CreateStatblockResponseV1.model_validate_json(
        (API_FIXTURES / "create-response.json").read_text(encoding="utf-8")
    )
    StatblockRevisionResourceV1.model_validate_json(
        (API_FIXTURES / "exact-revision-response.json").read_text(encoding="utf-8")
    )
    ErrorEnvelopeV1.model_validate_json(
        (API_FIXTURES / "errors.json").read_text(encoding="utf-8")
    )
    human = StatblockDefinitionV1.model_validate_json(
        HUMAN_FIXTURE.read_text(encoding="utf-8")
    )
    summary = combat_minimums(human)
    assert summary["human_adjudicated_elements"], "human_adjudicated fixture must project"
    return summary


def exercise(client: TestClient, headers: dict[str, str]) -> None:
    from statblocks_v1.application.projection import combat_minimums
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

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

    summary = combat_minimums(StatblockDefinitionV1.model_validate(definition))
    assert summary["armor_class"] is not None
    assert summary["hit_points"] is not None
    print(
        "smoke passed:",
        statblock_id,
        first_id,
        second["revision_id"],
        summary["name"],
        summary["armor_class"],
        summary["hit_points"],
    )


def offline(*, compile_client: bool = True) -> None:
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

    if compile_client:
        compile_generated_client()
    parse_api_fixtures_and_human_adjudicated()

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
        "--skip-client-compile",
        action="store_true",
        help="Skip generated TypeScript compile.",
    )
    args = parser.parse_args()
    if args.base_url and not args.live:
        parser.error("--base-url requires --live to prevent accidental production writes")
    compile_client = not args.skip_client_compile
    if not args.base_url:
        offline(compile_client=compile_client)
        return
    key = os.getenv("DUNGEONBUDDY_INTERNAL_API_KEY")
    if not key:
        parser.error("DUNGEONBUDDY_INTERNAL_API_KEY is required for --live")
    if compile_client:
        compile_generated_client()
    parse_api_fixtures_and_human_adjudicated()
    import httpx

    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        exercise(client, {"X-DungeonBuddy-Internal-Key": key})  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
