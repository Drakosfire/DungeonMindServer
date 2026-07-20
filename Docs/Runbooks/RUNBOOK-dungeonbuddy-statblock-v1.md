# DungeonBuddy statblock v1 launch runbook

Read `Docs/Guides/CONFIG-dungeonbuddy-statblock-v1.md` before deployment.
The authoritative client contract is
`openapi/dungeonbuddy-statblocks-v1.json`; regenerate it with:

```bash
PYTHONPATH=. uv run --isolated --no-project --with 'fastapi==0.115.6' \
  --with 'pydantic==2.7.4' --with 'httpx==0.28.1' --with 'starlette==0.41.3' \
  python scripts/export_dungeonbuddy_statblock_openapi.py
```

Use the committed `uv.lock` for reproducible environments:

```bash
uv sync --locked
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

There is no Dockerfile in this repository at this commit, so no untested image
build change is made. A future image should copy `pyproject.toml` and `uv.lock`
before source and install with `uv sync --locked`, rather than compiling a new
resolution during the image build.

Check liveness without credentials:

```bash
curl -fsS http://HOST:8000/api/internal/dungeonbuddy/v1/statblocks/health/live
```

Then use the internal key to check readiness/capabilities and run the default
offline smoke:

```bash
uv run python scripts/smoke_dungeonbuddy_statblock_v1.py
```

The smoke compiles `generated/dungeonbuddy-statblocks-v1/client.ts`, parses the
published API fixtures plus `human_adjudicated`, then exercises generate →
candidate read → validate → create → exact revision read → append → list →
reread first revision → combat minimums. Idempotency keys are unique per run.
It uses `TestClient`, in-memory repositories, and a fake provider by default and
writes no external state.

A remote smoke is deliberately opt-in because it creates a disposable
statblock. Always use unique keys (the script already does):

```bash
DUNGEONBUDDY_INTERNAL_API_KEY=... uv run python scripts/smoke_dungeonbuddy_statblock_v1.py \
  --live --base-url https://staging.example
```

Operational triage: use `X-Request-ID` from a response to locate structured
logs. Request logs include route, exact `outcome_code`, allocated
candidate/statblock/revision IDs when present, validation issue counts,
provider/model/schema fingerprint and provider latency/tokens when available,
and total request latency. They must not include keys, prompts, definitions, or
provider response bodies. Operation logs (`statblocks_v1_operation`) record
allocation and digest identifiers after successful writes.

`504 provider_timeout` and `429 rate_limited` are retryable client outcomes
only with the original idempotency key. Do not retry `422` refusals or semantic
validation errors.

For an indeterminate create/append after a client timeout, repeat the identical
request with the identical idempotency key. The returned result is the original
outcome; a different request with that key is a `409 idempotency_conflict`.

Settings are operational: `STATBLOCKS_V1_FIRESTORE_ENABLED=false` blocks
persistence construction; `STATBLOCKS_V1_ASSET_GATEWAY_ENABLED=true` requires an
injected asset pipeline at composition time; provider timeout/retry/TTL come
from settings into `GenerationServiceV1`; log level is applied to the v1 logger.

Rollback generation by setting `STATBLOCKS_V1_FEATURE_ENABLED=false` while
keeping Firestore and `STATBLOCKS_V1_ALLOW_READS_WHEN_DISABLED=true`, then
redeploy. This returns a clear generation-disabled response while preserving
exact revisions. To roll back code, redeploy the prior known-good server
commit/configuration; legacy routes are deliberately not touched by PR20.
