# Revise idempotency fixtures (SBW06a)

StrictModel-valid v1 transport evidence for `POST .../statblock-candidates:revise`.
No secrets, no absolute paths, no live corpus. Parsing coverage lives in
`tests/statblocks_v1/test_api_fixtures.py`.

## Files

- `revise-request.json` — `ReviseCandidateRequestV1` with inline `source_definition` (`simple_bruiser`).
- `revise-replay-response.json` — full `GeneratedStatblockCandidateV1` (definition + validation + generation receipts).
- `revise-conflict-response.json` — `ErrorEnvelopeV1` for `409` / `idempotency_conflict` (matches `envelope_for(IdempotencyConflictError(...))`).

## Regenerate (model-valid)

From the DungeonMindServer repo root:

```bash
uv run python <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path

from statblocks_v1.api.http_errors import envelope_for
from statblocks_v1.api.models import ReviseCandidateRequestV1
from statblocks_v1.application.commands import CallerProvenanceV1, ReviseStatblockCommandV1
from statblocks_v1.application.generation import GenerationServiceV1, GenerateOutcomeV1
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

ROOT = Path("Docs/Design/fixtures")
DEF_DIR = ROOT / "dungeonbuddy-statblock-v1"
API_DIR = ROOT / "dungeonbuddy-statblock-v1-api"
CANDIDATE_ID = "cand_fix00000001"

bruiser = StatblockDefinitionV1.model_validate(
    json.loads((DEF_DIR / "simple_bruiser.json").read_text(encoding="utf-8"))
)
request = ReviseCandidateRequestV1(
    request_id="fixture-revise-source-def-1",
    ruleset=RulesetRef(system="dnd5e", edition="2024"),
    revision_instructions=["Tighten melee damage for table pace."],
    source_definition=bruiser,
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
command = ReviseStatblockCommandV1(
    request_id=request.request_id,
    ruleset=request.ruleset,
    revision_instructions=list(request.revision_instructions),
    caller=CallerProvenanceV1(caller_scope="dungeonbuddy", actor="fixture"),
    source_definition=bruiser,
)
service = GenerationServiceV1(
    provider=provider,
    candidates=candidates,
    settings=GenerationSettingsV1("test-model", 1, 0, 60),
    clock=lambda: now,
    candidate_id_factory=lambda: CANDIDATE_ID,
    generate_operations=gen_ops,
    revise_operations=rev_ops,
)
outcome = service.revise(command)
assert isinstance(outcome, GenerateOutcomeV1)
(API_DIR / "revise-replay-response.json").write_text(
    json.dumps(outcome.candidate.model_dump(mode="json"), indent=2) + "\n",
    encoding="utf-8",
)
(API_DIR / "revise-conflict-response.json").write_text(
    json.dumps(envelope_for(IdempotencyConflictError(request.request_id)), indent=2) + "\n",
    encoding="utf-8",
)
print("wrote revise idempotency fixtures")
PY

uv run pytest tests/statblocks_v1/test_api_fixtures.py -q
```
