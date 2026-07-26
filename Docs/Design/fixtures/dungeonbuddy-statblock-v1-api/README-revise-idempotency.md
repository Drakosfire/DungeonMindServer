# Revise idempotency fixtures (SBW06a)

StrictModel-valid v1 transport evidence for `POST .../statblock-candidates:revise`.
No secrets, no absolute paths, no live corpus. Parsing + cross-fixture coherence
coverage lives in `tests/statblocks_v1/test_api_fixtures.py`.

## Files

- `revise-request.json` — `ReviseCandidateRequestV1` with inline `source_definition` (`simple_bruiser`) and `actor: "fixture"`.
- `revise-replay-response.json` — full `GeneratedStatblockCandidateV1` captured from the FastAPI revise route for that request.
- `revise-conflict-response.json` — `ErrorEnvelopeV1` for `409` / `idempotency_conflict` (matches `envelope_for(IdempotencyConflictError(...))`).

The request/response pair is mutually coherent: route mapping uses
`CallerProvenanceV1(caller_scope="dungeonbuddy", actor=request.actor)`, so the
computed revise digest equals `generation_receipt.request_digest`, and actors /
request IDs / source-definition digests match.

## Regenerate (model-valid, FastAPI-captured)

From the DungeonMindServer repo root. If local Pydantic drift marks the OpenAI
strict schema artifact stale, regenerate artifacts for the capture only, then
revert them before committing (`git checkout HEAD -- statblocks_v1/domain/schema_artifacts/`).

```bash
uv run python <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ["DUNGEONBUDDY_INTERNAL_API_KEY"] = "fixture-regen-key"
os.environ["OPENAI_API_KEY"] = "test-openai-key"

from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import (
    get_candidate_repository,
    get_clock,
    get_generation_service,
)
from statblocks_v1.api.http_errors import envelope_for
from statblocks_v1.api.models import ReviseCandidateRequestV1
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.errors import IdempotencyConflictError
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import (
    InMemoryCandidateGenerationOperationRepository,
    InMemoryCandidateRevisionOperationRepository,
    InMemoryCandidateRepository,
)
from statblocks_v1.testing import create_test_app

ROOT = Path("Docs/Design/fixtures")
DEF_DIR = ROOT / "dungeonbuddy-statblock-v1"
API_DIR = ROOT / "dungeonbuddy-statblock-v1-api"
CANDIDATE_ID = "cand_fix00000001"
INTERNAL_KEY = "fixture-regen-key"

bruiser = StatblockDefinitionV1.model_validate(
    json.loads((DEF_DIR / "simple_bruiser.json").read_text(encoding="utf-8"))
)
request = ReviseCandidateRequestV1(
    request_id="fixture-revise-source-def-1",
    ruleset=RulesetRef(system="dnd5e", edition="2024"),
    revision_instructions=["Tighten melee damage for table pace."],
    source_definition=bruiser,
    actor="fixture",
)
(API_DIR / "revise-request.json").write_text(
    json.dumps(request.model_dump(mode="json"), indent=2) + "\n",
    encoding="utf-8",
)

now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
provider = FakeDefinitionProvider(bruiser.model_dump(mode="json"))
candidates = InMemoryCandidateRepository(clock=lambda: now)
rev_ops = InMemoryCandidateRevisionOperationRepository(candidates, clock=lambda: now)
gen_ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
service = GenerationServiceV1(
    provider=provider,
    candidates=candidates,
    settings=GenerationSettingsV1("test-model", 1, 0, 60),
    clock=lambda: now,
    candidate_id_factory=lambda: CANDIDATE_ID,
    generate_operations=gen_ops,
    revise_operations=rev_ops,
)
app = create_test_app()
app.dependency_overrides[get_generation_service] = lambda: service
app.dependency_overrides[get_candidate_repository] = lambda: candidates
app.dependency_overrides[get_clock] = lambda: (lambda: now)

client = TestClient(app)
response = client.post(
    "/api/internal/dungeonbuddy/v1/statblock-candidates:revise",
    json=request.model_dump(mode="json"),
    headers={"X-DungeonBuddy-Internal-Key": INTERNAL_KEY},
)
assert response.status_code == 200, response.text
payload = response.json()
assert payload["candidate_id"] == CANDIDATE_ID
assert payload["generation_receipt"]["actor"] == request.actor
(API_DIR / "revise-replay-response.json").write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)
(API_DIR / "revise-conflict-response.json").write_text(
    json.dumps(envelope_for(IdempotencyConflictError(request.request_id)), indent=2) + "\n",
    encoding="utf-8",
)
print("wrote revise idempotency fixtures via FastAPI route")
PY

uv run pytest tests/statblocks_v1/test_api_fixtures.py -q
```
