# Plan: DungeonBuddy Statblock v1 Route Roadmap

**Status:** ACTIVE  
**Created:** 2026-07-17  
**Repository:** `Drakosfire/DungeonMindServer`  
**Contract:** `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md`  
**Architecture audit:** `Docs/Design/AUDIT-dungeonbuddy-statblock-v1-route-readiness.md`  
**Planned PR range:** PR12–PR21

## 1. Mission

Stand up the DungeonMindServer-owned statblock v1 route consumed by DungeonBuddy, beginning with an independently testable bounded context and ending with production-ready generation, validation, immutable revision persistence, exact replay, asset references, generated consumer types, and deployment verification.

This plan also improves the repository where improvement directly supports the route. It does not turn the route into an excuse to rewrite every existing DungeonMind product.

## 2. Product completion definition

The route is complete when DungeonBuddy can:

```text
send a typed generation request
→ receive a typed GeneratedStatblockCandidateV1
→ edit the complete StatblockDefinitionV1
→ validate that definition
→ create a logical statblock and first immutable revision
→ append a later immutable revision
→ read the exact revision by ID
→ receive the same canonical mechanics and digest on replay
→ consume generated OpenAPI types
→ bind the exact revision into a Threat, Plan, scene, or combatant
```

The route is not complete merely because OpenAI returns JSON or a FastAPI handler returns 200.

## 3. Sequencing principles

1. **Bounded context before endpoints.** New v1 code does not land in the legacy statblock router.
2. **Pure domain before infrastructure.** Models, canonicalization, validation, and digest behavior must be testable without network or credentials.
3. **Persistence before acceptance.** A candidate route may exist before revisions, but DungeonBuddy acceptance is not enabled until immutable persistence exists.
4. **One schema.** Structured Outputs, API editing, validation, and revision storage share `StatblockDefinitionV1`.
5. **Fake first, real second.** Every provider and repository is exercised through a fake or in-memory implementation before external integration.
6. **Exact replay is the trust milestone.** The route becomes authoritative only when a revision can be read back exactly with a stable digest.
7. **Generated consumer types.** DungeonBuddy does not hand-copy the contract.
8. **No hidden migration.** Legacy project/session documents and old routes remain untouched until explicit post-launch cleanup.

## 4. PR dependency graph

```text
PR12 bounded-context foundation
  ↓
PR13 contract models + fixtures
  ↓
PR14 canonicalization + validation + digest
  ↓
PR15 repositories + persistence
  ↓
PR16 Structured Outputs generation service
  ↓
PR17 candidate API
  ↓
PR18 revision resource API
  ↓
PR19 assets + OpenAPI + consumer contract
  ↓
PR20 production hardening + launch
  ↓
PR21 legacy quarantine + repo hygiene (post-launch)
```

PR15 and PR16 may be developed in parallel after PR14, but PR17 requires both.

## 5. PR scorecard

| PR | Deliverable | Route availability | External dependency | Completion signal |
|---|---|---|---|---|
| 12 | Clean package, dependency seams, isolated tests, v1 health stub | Health only | None | Tests run without Firebase/OpenAI |
| 13 | Complete Pydantic contract and representative fixtures | Health/schema discovery | None | All fixtures validate and schema snapshot is stable |
| 14 | Canonicalization, semantic validation, digest | Validate service internally | None | Equivalent definitions digest identically |
| 15 | Candidate/statblock/revision repositories and Firestore layout | No public write route | Firestore adapter | Immutable append and replay pass repository tests |
| 16 | Structured Outputs compiler, prompt builder, generation service | No HTTP generation yet | OpenAI adapter | Fake provider and gated live smoke produce v1 definition |
| 17 | Generate, revise, validate candidate endpoints | Candidate routes live | OpenAI + candidate repository | Typed candidate and failure envelopes pass route tests |
| 18 | Create/read/list/append revision endpoints | Authoritative resource routes live | Firestore | Exact persisted revision replay and idempotency pass |
| 19 | Asset references, OpenAPI artifact, DungeonBuddy generated client contract | Full contract consumable | Cloudflare bridge | Cross-repo contract smoke passes |
| 20 | Observability, auth hardening, deployment, end-to-end smoke | Production-ready | Production services | DungeonBuddy-to-production exact-revision smoke passes |
| 21 | Legacy quarantine and repository hygiene | No v1 behavior change | None | Active docs and modules are unambiguous |

## 6. PR12 — bounded-context foundation

**Handoff:** `Docs/Plans/HANDOFF-pr12-statblock-v1-bounded-context-foundation.md`

Create the package boundary and test seam before adding the detailed schema.

Required outcomes:

- a `statblocks_v1` package with domain/application/infrastructure/api layers or an equivalently explicit structure;
- no domain import of FastAPI, OpenAI, Firebase, Cloudflare, or legacy statblock modules;
- protocols or callable dependencies for provider, repositories, IDs, clock, and assets;
- an isolated FastAPI test app around the v1 router;
- router-level internal auth;
- a health/capability endpoint advertising the contract as unavailable or foundation-only;
- focused CI or a reproducible command that runs without the full production dependency graph;
- no functional generation or persistence yet.

This PR is intentionally architectural. It must not pretend the route is implemented.

## 7. PR13 — contract models and fixtures

**Handoff:** `Docs/Plans/HANDOFF-pr13-statblock-v1-contract-models-fixtures.md`

Translate the design into executable Pydantic models.

Required fixture families:

- simple bruiser;
- spellcaster;
- legendary creature;
- lair creature;
- unusual movement;
- mythic phase;
- human-adjudicated mechanic;
- invalid duplicate key;
- invalid dangling reference;
- invalid section/activation combination.

The contract should produce canonical JSON Schema and an OpenAI-compatible schema artifact, but provider calls remain out of scope.

## 8. PR14 — canonicalization, validation, and digest

**Handoff:** `Docs/Plans/HANDOFF-pr14-statblock-v1-canonicalization-validation-digest.md`

Implement the trust core.

Validation layers:

```text
structural Pydantic validation
cross-field/domain validation
ruleset derivation checks
reference integrity
rules text/typed semantic contradiction warnings or errors
persistence readiness decision
```

Canonicalization must define:

- deterministic key ordering;
- treatment of empty versus omitted optionals;
- stable list ordering where order is semantic;
- stable normalization where order is not semantic;
- canonical dice and CR serialization;
- digest algorithm and version.

No infrastructure or HTTP route should own these rules.

## 9. PR15 — repositories and immutable persistence

**Handoff:** `Docs/Plans/HANDOFF-pr15-statblock-v1-repositories-persistence.md`

Create repository protocols, in-memory implementations, and Firestore adapters for:

- candidates with expiration;
- logical statblocks;
- append-only revisions;
- idempotency records.

The PR must define Firestore collection/document layout and transaction boundaries.

Core invariants:

```text
accepted revision content never mutates
revision IDs are server allocated
parent revision must exist for append
idempotency retries return the original outcome
digest collision or mismatched retry is rejected
exact revision read returns persisted canonical definition
```

No legacy project document is used as a v1 revision.

## 10. PR16 — Structured Outputs generation service

**Handoff:** `Docs/Plans/HANDOFF-pr16-statblock-v1-structured-generation-service.md`

Implement:

- generation request application model;
- prompt builder driven by v1 intent and ruleset;
- canonical Pydantic-to-OpenAI schema compiler;
- provider protocol;
- OpenAI provider adapter;
- fake provider;
- generation receipt;
- candidate creation service;
- revise-from-definition/revision service.

The model returns `StatblockDefinitionV1`, not the outer candidate or revision envelope.

Live provider tests are opt-in and never required for ordinary CI.

## 11. PR17 — candidate API

**Handoff:** `Docs/Plans/HANDOFF-pr17-statblock-v1-candidate-api.md`

Stand up:

```text
POST /api/internal/dungeonbuddy/v1/statblock-candidates:generate
POST /api/internal/dungeonbuddy/v1/statblock-candidates:revise
POST /api/internal/dungeonbuddy/v1/statblock-definitions:validate
GET  /api/internal/dungeonbuddy/v1/statblock-candidates/{candidate_id}
```

The generate and revise routes persist candidate records so a later acceptance does not trust client-supplied provenance.

The candidate API returns no canonical Markdown and no copied combat-defaults object.

## 12. PR18 — revision resource API

**Handoff:** `Docs/Plans/HANDOFF-pr18-statblock-v1-revision-resource-api.md`

Stand up authoritative persistence routes:

```text
POST /api/internal/dungeonbuddy/v1/statblocks
POST /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{revision_id}
```

Creation and append accept the complete proposed definition and optional candidate locator. DungeonMindServer validates and canonicalizes again before persistence.

This PR is the first point where DungeonBuddy may safely accept a candidate into durable mechanics truth.

## 13. PR19 — assets, OpenAPI, and consumer contract

**Handoff:** `Docs/Plans/HANDOFF-pr19-statblock-v1-assets-openapi-consumer-contract.md`

Connect the v1 contract to existing asset infrastructure without moving image-selection ownership away from DungeonBuddy.

Required outcomes:

- typed `AssetRefV1` and `AssetBriefV1` behavior;
- optional candidate asset references;
- revision asset bindings that do not affect mechanics digest unless explicitly contract-defined;
- deterministic OpenAPI export or checked schema artifact;
- generated DungeonBuddy TypeScript client/types;
- cross-repository fixture verification;
- explicit detection of contract drift.

This PR may require a small coordinated DungeonMindBuddy PR, but DungeonMindServer remains authoritative.

## 14. PR20 — production hardening and launch

**Handoff:** `Docs/Plans/HANDOFF-pr20-statblock-v1-production-hardening-launch.md`

Make the route operable rather than merely correct in tests.

Required areas:

- typed error-to-HTTP mapping;
- request IDs and idempotency logs;
- latency and provider timing metrics;
- safe structured logs without full prompts, secrets, or statblock payload dumps;
- router-level service authentication;
- configuration validation;
- health and readiness semantics;
- Firestore indexes/TTL configuration;
- timeout and retry policy;
- Docker and deployment verification;
- end-to-end DungeonBuddy smoke.

Launch does not retire old routes.

## 15. PR21 — legacy quarantine and repository hygiene

**Handoff:** `Docs/Plans/HANDOFF-pr21-statblock-legacy-quarantine-repo-hygiene.md`

This is post-launch and not a route gate.

Goals:

- split or clearly mark the legacy statblock router;
- remove duplicate health declarations;
- mark v2 command-board contract as superseded for DungeonBuddy;
- clarify active versus legacy docs;
- remove committed generated artifacts where safe;
- update README from “microservices” rhetoric to the actual deployment shape;
- improve dependency grouping and Docker lockfile use where safely separable;
- document broader app-factory and startup-lifecycle debt for later work.

Do not delete working legacy routes without an explicit consumer audit.

## 16. Cross-PR invariants

Every PR must preserve:

- no backwards compatibility obligation for the new v1 contract;
- no mutation of accepted revisions;
- no browser access to privileged internal routes;
- no DungeonBuddy-owned canonical mechanics schema;
- no hidden canonical Markdown;
- no acceptance without server validation;
- no exact revision read resolved through “latest”;
- no import-time Firebase/OpenAI requirement in pure contract tests;
- no claim of full automation for `human_adjudicated` mechanics.

## 17. Testing ladder

### Level A — pure domain

Runs on every PR from PR13 onward.

```text
model validation
reference integrity
canonicalization
digests
semantic validation
fixture round trips
```

### Level B — application services

Uses fake providers, in-memory repositories, deterministic IDs, and a frozen clock.

### Level C — isolated HTTP

Creates a tiny FastAPI app with the v1 router only and dependency overrides.

### Level D — infrastructure integration

Uses Firestore emulator/test project and opt-in provider tests.

### Level E — production smoke

Runs only with explicitly configured production/staging credentials and records no sensitive payloads.

## 18. Failure policy

A PR is not complete when:

- pytest did not run and only compilation passed;
- a test requires production credentials without a fake alternative;
- route code directly constructs Firebase or OpenAI clients;
- a retry can create duplicate revisions;
- schema or fixture drift is unreviewed;
- a generated candidate is treated as an accepted revision;
- a new route imports the legacy statblock router to obtain global state.

## 19. Successor handoff policy

Each PR must update its successor handoff with:

- actual merged commit;
- files and symbols created;
- deviations from this plan;
- unresolved risks;
- exact verification command;
- fixtures or IDs the next PR should reuse.

The roadmap is a sequence of contracts between coding agents, not merely a checklist.
