# HANDOFF — PR20 Statblock v1 production hardening and launch

**Status:** READY AFTER PR19  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Coordinated consumer:** `Drakosfire/DungeonMindBuddy`  
**Predecessor:** PR19 assets/OpenAPI/consumer contract  
**Successor:** `HANDOFF-pr21-statblock-legacy-quarantine-repo-hygiene.md`

## PR19 predecessor completion notes

- The authoritative isolated artifact is
  `openapi/dungeonbuddy-statblocks-v1.json` (schema fingerprint
  `sha256:22ab847ac7197055ae1ef12c287d39a99cd720a8e03cd9856bfc3e3259e0cce2`).
  Regenerate it, its fixtures, and the checked-in consumer client with
  `PYTHONPATH=. uv run --isolated --no-project --with 'fastapi==0.115.6'
  --with 'pydantic==2.7.4' --with 'httpx==0.28.1' --with 'starlette==0.41.3'
  python scripts/export_dungeonbuddy_statblock_openapi.py`.
- Resource envelopes and health publish the package contract identity as
  **required** exact literals (`dungeonmind.dungeonbuddy-statblocks` / `1.0.0`),
  matching the design header — not the obsolete `dungeonbuddy-statblock` / `v1`
  pair. Missing or incorrect identities fail validation; OpenAPI marks both
  fields required and the generated client exposes them without `?`.
- The generated TypeScript contract/client is
  `generated/dungeonbuddy-statblocks-v1/client.ts`. Component names with
  OpenAPI hyphens are sanitized to valid identifiers (`AssetBindingV1_Input`),
  `allOf` refs preserve enums (for example `Distance.unit` → `DistanceUnit`),
  nullable branches render as `| null` (not `| unknown`), and the focused
  lane exact-compares the client text to the exporter output. Consumer
  projects must import these generated transport types rather than maintaining
  copies.
- Published API fixtures match live route semantics: the generate-request /
  candidate-response pair is one deterministic generation-service exchange
  (omitted actor/asset_options → null actor, no images, brief and source
  digest derived from the request description); validate responses use
  `editor_preview`; accepted revisions use `persistence`; and the public error
  fixture uses `validation_failed` with the full persistence
  receipt/`is_persistence_ready` details.
- The final v1 resource operation IDs are `create_statblock_v1`,
  `append_statblock_revision_v1`, `get_statblock_v1`,
  `list_statblock_revisions_v1`, and `get_statblock_revision_v1`; candidate
  operation IDs remain published in the same artifact.
- Asset references are typed CDN-backed `AssetRefV1` values. Firestore encoding
  stringifies `HttpUrl`/`Url` while preserving native datetime timestamps.
  The optional `CloudflareAssetGateway` receives an injected pipeline callable
  and requires it to return durable IDs and canonical URLs; PR20 owns
  environment wiring, timeouts, and production failure telemetry. Asset
  failures only warn and do not invalidate otherwise valid candidate mechanics.
- A DungeonBuddy smoke should regenerate/import the checked-in client, parse
  `Docs/Design/fixtures/dungeonbuddy-statblock-v1-api/`, and retain exact
  `statblock_id + revision_id` locators before launch. **This coordinated
  consumer compile/parse/projection/`human_adjudicated` proof is intentionally
  owned by PR20** — PR19 publishes the contract artifact and fixtures but does
  not require a live DungeonBuddy checkout to merge.

## 0. Mission

Make the complete DungeonBuddy statblock v1 route safe and observable in the deployed DungeonMindServer environment, then prove the end-to-end authoring, acceptance, and exact-replay workflow from DungeonBuddy.

This PR launches the new route. It does not retire legacy routes.

## 1. Configuration

Create explicit validated settings for the v1 bounded context, including:

```text
service authentication key/current identity
OpenAI API key and model
provider timeout/retry limits
candidate TTL
Firestore collection names or namespace
asset gateway settings
feature-enable flag
logging/metrics options
```

Configuration errors should fail readiness for the v1 capability without dumping secrets.

Avoid logging environment values or full credentials.

## 2. Authentication hardening

Router-level service authentication remains mandatory.

At minimum:

- constant-time key comparison;
- no browser exposure;
- safe 401/403/503 distinctions;
- caller service identity in request context and provenance;
- documented key rotation procedure;
- no request payload accepted before auth dependency succeeds.

A more elaborate identity platform is not required unless existing deployment architecture already provides one cleanly.

## 3. Timeouts and retries

Define explicit policy for:

- provider connection/read timeout;
- provider rate limit;
- transient provider retry count/backoff;
- Firestore transaction retry;
- asset-generation timeout;
- DungeonBuddy client retry using request/idempotency keys.

Do not retry semantic validation failures or provider refusals.

## 4. Observability

Add structured logs and/or metrics for:

```text
operation and route
request/correlation ID
caller service
candidate/statblock/revision IDs after allocation
outcome/error code
provider/model/prompt/schema versions
validation status and issue counts
latency by provider, validation, persistence, assets
token/cost data where safely available
idempotency replay/conflict
```

Do not log:

- internal authentication key;
- full hidden provider response;
- complete statblock payload by default;
- full authored threat description when it may contain campaign-private content;
- service account credentials.

## 5. Health and readiness

Distinguish:

```text
liveness
  process/router responds

readiness
  auth configuration, provider, persistence, and required contract artifacts are configured

capability discovery
  exact implemented v1 operations and contract version
```

Provider availability may be reported as degraded rather than making all exact-revision reads unavailable. Read-only persisted-resource routes should remain usable when OpenAI is down.

## 6. Firestore operations

Ensure production configuration includes:

- required indexes;
- candidate TTL policy;
- collection permissions/service account access;
- transaction/retry behavior;
- backup/export considerations for immutable revisions;
- no accidental public access;
- operational query for candidate/statblock/revision lookup.

Document how to inspect and reconcile an indeterminate write outcome using idempotency records.

## 7. Docker and dependency behavior

Verify the deployed image can start and serve the v1 route reproducibly.

This PR should prefer installing from the committed lockfile or otherwise document why the current Docker compile path remains necessary.

Do not force the v1 test lane to download unrelated large ML models.

Record:

- exact build command;
- exact server start command;
- required environment variables;
- container port/path;
- health checks;
- rollback commit/process.

## 8. End-to-end smoke

Run a configured smoke through the real server boundary:

```text
DungeonBuddy-authenticated generate request
→ candidate read
→ edited or unchanged definition validation
→ create logical statblock + first revision
→ exact revision read
→ append second revision
→ read both revisions
→ verify first unchanged and both digests stable
→ derive DungeonBuddy summary/combat minimums
```

The smoke may use staging or production according to deployment safety. Use a clearly named disposable test statblock and preserve IDs in the verification record.

## 9. Failure drills

Verify typed behavior for:

- wrong/missing auth;
- OpenAI unavailable;
- provider timeout;
- validation failure;
- Firestore unavailable;
- idempotent retry after client timeout;
- candidate expired;
- exact revision not found;
- asset generation failure while mechanics generation succeeds.

## 10. Documentation

Add or update:

- v1 route runbook;
- environment configuration reference;
- local development instructions;
- focused test commands;
- Firestore emulator/integration instructions;
- deployment and rollback steps;
- DungeonBuddy client version/fingerprint;
- known limitations, especially human-adjudicated mechanics.

Do not replace the authoritative contract design with a deployment README.

## 11. Suggested files

```text
statblocks_v1/config.py
statblocks_v1/api/health.py
statblocks_v1/observability.py
Docs/Runbooks/RUNBOOK-dungeonbuddy-statblock-v1.md
Docs/Guides/CONFIG-dungeonbuddy-statblock-v1.md
scripts/smoke_dungeonbuddy_statblock_v1.py
Dockerfile / deployment config as needed
tests/statblocks_v1/test_readiness.py
tests/statblocks_v1/test_observability.py
```

## 12. Testing requirements

Mandatory:

- all pure/application/route tests from prior PRs;
- production dependency composition test with fake infrastructure;
- readiness permutations;
- auth before body/service invocation;
- timeout/retry policy tests;
- idempotency retry drill;
- exact replay smoke;
- generated OpenAPI drift check;
- DungeonBuddy generated-client compile/smoke.

Gated live tests must be clearly opt-in and skip safely without credentials.

## 13. Launch acceptance criteria

PR20 is complete when:

- route is deployed or deployment-ready under a documented feature flag;
- DungeonBuddy can complete the full candidate-to-revision workflow;
- exact revision replay survives process/service restart;
- provider outage does not break persisted revision reads;
- logs identify failures without leaking secrets/private payloads;
- idempotent retries cannot duplicate revisions;
- readiness accurately reports missing infrastructure;
- rollback is documented and tested to the practical extent possible;
- old routes remain operational and unchanged unless explicitly noted.

## 14. Non-goals

- no legacy route deletion;
- no full server modularization;
- no public API launch;
- no automated execution of every rule element;
- no DungeonBuddy graph migration.

## 15. Successor handoff

Before merge, update PR21 with:

- deployed route/version and commit;
- observed legacy confusion or duplication encountered during launch;
- files safe to quarantine/remove;
- current build/dependency constraints;
- active consumer inventory for old statblock routes;
- any cleanup that was deliberately deferred.
