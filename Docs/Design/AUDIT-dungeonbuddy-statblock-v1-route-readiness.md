# Audit: DungeonBuddy Statblock v1 Route Readiness

**Status:** ACTIVE ARCHITECTURE AUDIT  
**Created:** 2026-07-17  
**Repository:** `Drakosfire/DungeonMindServer`  
**Reviewed anchor:** `5455fb50a398dbc8965ceec494ab0dd0b356edb9`  
**Authoritative contract:** `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md`

## 1. Purpose

This audit evaluates the current DungeonMindServer architecture specifically against the work required to stand up the new DungeonBuddy statblock v1 contract.

It is intentionally scrutinizing. The repository contains useful production machinery, but much of its architecture reflects an earlier showcase application rather than a contract-owning backend with independently testable domain services.

The conclusion is not “rewrite the server.” The conclusion is:

```text
Build the new statblock contract as a clean bounded context.
Reuse proven infrastructure behind explicit adapters.
Do not make broad legacy cleanup a prerequisite.
Do not copy legacy coupling into the new route.
```

## 2. Executive assessment

The repository can support the new route, but not safely by adding more handlers to `routers/statblockgenerator_router.py`.

The current statblock implementation proves:

- OpenAI Structured Outputs can produce a Pydantic model;
- FastAPI routes can expose statblock generation;
- DungeonBuddy server-to-server authentication has a working precedent;
- Firestore is available for durable storage;
- Cloudflare-backed image URLs are available;
- fixtures and focused route tests can be written;
- the existing frontend and combat prototype have useful behavior to preserve through new projections.

The current implementation also has structural problems that would make the new contract brittle if copied:

- import-time initialization of external services;
- a single application process coupled to unrelated products;
- one oversized statblock router mixing HTTP, generation, persistence, image management, validation, project state, and compatibility routes;
- canonical mechanics mixed with workflow and project fields;
- synchronous Firestore calls inside async handlers;
- route tests coupled to global modules and credentials;
- non-reproducible or excessively broad dependency installation;
- no clean repository or service abstraction for immutable revisions;
- documentation that describes a microservice architecture while the server behaves as a modular monolith.

## 3. Current architecture findings

### 3.1 The runtime is a modular monolith, not independent microservices

`app.py` imports and registers Rules Lawyer, CardGenerator, image management, assets, global sessions, global objects, StatBlockGenerator, PlayerCharacterGenerator, demo routes, maps, SMS, auth, sessions, and stores into one FastAPI application.

That is not inherently wrong. A modular monolith can be an excellent deployment shape. The problem is that the repository and documentation often reason as though these modules are independently isolated services when they share one process, one dependency graph, and import-time startup behavior.

For the new route, the accurate operating model is:

```text
one deployed FastAPI process
containing several product modules
with a new independently testable statblock bounded context
```

The roadmap must not depend on extracting a new microservice.

### 3.2 Import-time side effects make unrelated failures contagious

Current imports can initialize:

- environment files;
- global OpenAI clients;
- a global `StatBlockGenerator`;
- `RulesLawyerService`;
- Firebase Admin and Firestore from a credential file;
- other product routers and their dependencies.

This means a unit test for a statblock request model can fail because Firebase credentials, embeddings, a model package, or an unrelated service is unavailable.

The new bounded context must therefore permit:

```text
import domain models
import canonicalization
import validators
instantiate an isolated FastAPI router
run tests
```

without requiring Firebase, OpenAI, Rules Lawyer embeddings, Cloudflare, or the full `app.py` import graph.

### 3.3 Application lifecycle intent and runtime wiring disagree

`app.py` defines a lifespan function intended to preload Rules Lawyer embeddings, but constructs the application with `FastAPI()` rather than `FastAPI(lifespan=lifespan)`.

This audit does not prescribe fixing Rules Lawyer as part of the statblock route. It records the mismatch as evidence that startup responsibilities are not centrally controlled or reliably exercised.

The new statblock context should not add additional hidden startup behavior. Infrastructure clients should be created through explicit dependencies or application composition.

### 3.4 The statblock router is an architectural dumping ground

`routers/statblockgenerator_router.py` currently owns or directly coordinates:

- health routes;
- legacy statblock generation;
- v2 DungeonBuddy draft generation;
- rendering Markdown drafts;
- validation;
- challenge-rating calculation;
- user image upload;
- bulk image upload;
- image deletion;
- project creation and listing;
- project loading and deletion;
- project save normalization;
- session save/load;
- Firestore collection names;
- global OpenAI and generator instances;
- direct Firestore access;
- direct Cloudflare and HTTP calls.

It also defines `/health` twice in the same router.

The new route must not be added to this file. It should have its own router and application service boundary.

### 3.5 Current domain models conflate mechanics, transport, and workflow

`StatBlockDetails` contains useful mechanics, but also includes:

- project ID;
- created and modified timestamps;
- tags;
- a Stable Diffusion prompt;
- presentation-oriented description;
- camelCase aliases for a frontend contract.

The same module also defines project, session, generation request, image response, validation request, and workflow-state models.

The new contract correctly separates:

```text
StatblockDefinitionV1
  canonical mechanics

GeneratedStatblockCandidateV1
  generation proposal and receipts

StatblockRevisionResourceV1
  immutable server identity and persistence

DungeonBuddy projections
  rendering, summaries, combat seed, graph use
```

### 3.6 The existing `Action` model is too shallow

The shared action shape contains mostly prose plus optional attack bonus, damage string, damage type, range, and recharge.

It is then reused for:

- actions;
- bonus actions;
- reactions;
- traits;
- legendary actions;
- lair actions.

This loses the distinction between presentation section, activation timing, resource cost, target, save, attack, effects, phases, and automation support.

The v1 contract’s orthogonal rule-element design is therefore a replacement, not a compatible extension.

### 3.7 Generation and validation are not dependency-injected

`StatBlockGenerator` creates its OpenAI client from environment state and directly owns prompt construction, provider calls, schema cleaning, validation, and CR calculation.

The new implementation needs separate interfaces for:

```text
generation provider
prompt builder
structured-schema compiler
semantic validator
canonicalizer
candidate repository
revision repository
clock and ID allocation
```

This does not require abstracting every function. It requires enough separation that pure domain tests and fake-provider route tests are possible.

### 3.8 Persistence is mutable project storage, not immutable resource storage

Current project persistence overwrites a Firestore project document containing frontend workflow state. Manual session saves can create creature records, but there is no stable logical statblock with append-only revision lineage.

The new contract requires new collections and repository semantics. Legacy project documents should not be migrated or reused as revision resources.

### 3.9 Firestore access is synchronous and directly embedded in async routes

The Google Cloud Firestore client used by the current code is synchronous. Calls such as `.get()`, `.set()`, `.stream()`, and `.delete()` occur directly inside async route handlers.

For the first v1 implementation, correctness and isolation matter more than replacing Firestore. A repository adapter can encapsulate those calls and, where needed, run blocking operations outside the event loop. This behavior should be explicit and testable.

### 3.10 Test architecture is unreliable

The global `tests/conftest.py` imports the complete production app. Recent statblock PRs repeatedly reported that pytest could not execute because of missing `python-dotenv`, the git-based `GenerationEngine` dependency, or environment limitations.

The v2 route tests improve on this by constructing a small FastAPI app around the router, but importing the router still imports global Firestore and generator state.

The v1 contract needs three separate test levels:

```text
pure contract tests
  no FastAPI, OpenAI, Firestore, or credentials

isolated route tests
  tiny FastAPI app, fake services and repositories

infrastructure integration tests
  Firestore emulator or explicitly configured test project
```

No PR should claim route validation when only `py_compile` ran.

### 3.11 Dependency and build behavior are broader than necessary

The runtime project dependencies include large ML packages, pandas, NumPy, sentence-transformers, Firebase, MongoDB, Twilio, PDF tooling, image tooling, pytest, and a git-based `GenerationEngine` dependency.

A committed `uv.lock` exists, but the Dockerfile recompiles requirements from `pyproject.toml` rather than installing from the lock. This weakens reproducibility and forces every server build to resolve the entire application dependency graph.

The route roadmap should establish a focused CI lane that can test the contract without downloading unrelated ML or image dependencies. Broader dependency decomposition is valuable but should not block the route.

### 3.12 Prompt implementation contains schema drift

The current prompt contains examples and requirements that do not always match the current Pydantic model. One example instructs legendary actions to contain a `cost` field even though the shared `Action` model does not define that field.

The prompt is also tightly coupled to old top-level booleans and contains long illustrative content unrelated to many creatures.

The v1 generator must compile prompts from the new contract and validate representative outputs. Prompt versioning and model selection should be explicit receipts rather than hard-coded incidental strings.

### 3.13 Internal service authentication is a useful precedent, not the finished boundary

The current `X-DungeonBuddy-Internal-Key` dependency uses constant-time comparison and correctly keeps the key server-side.

For v1 it may be reused initially, but the route family should:

- apply one shared dependency at the router level;
- return the v1 typed error envelope;
- identify the calling service in provenance;
- avoid exposing configuration details;
- preserve a future path for key rotation or stronger service identity.

The route does not need a new authentication platform before it can ship.

### 3.14 Repository hygiene obscures the active architecture

The repository includes stale architecture prose, generated `egg-info`, VS Code counter artifacts, legacy compatibility layers, and old project documents. This makes navigation harder and increases the chance that an agent follows superseded guidance.

A post-launch cleanup PR should quarantine or remove clearly generated artifacts and mark old statblock documents as legacy. That cleanup should follow the working v1 route rather than creating a broad precondition.

## 4. Architecture decision for the new route

Create a new bounded context, tentatively:

```text
statblocks_v1/
  domain/
    models.py
    rule_elements.py
    primitives.py
    errors.py
  application/
    generation.py
    validation.py
    canonicalization.py
    revisions.py
  infrastructure/
    openai_provider.py
    firestore_repositories.py
    asset_gateway.py
  api/
    models.py
    dependencies.py
    router.py
```

Exact names may change, but these dependency rules are locked:

```text
domain
  imports no FastAPI, OpenAI, Firebase, Cloudflare, or legacy statblock modules

application
  depends on domain and narrow protocols

infrastructure
  implements protocols using current external systems

api
  converts HTTP requests to application commands and maps typed outcomes to responses

legacy statblockgenerator
  may be called only through an explicit temporary adapter when a PR intentionally reuses behavior
```

The new router should be mounted at:

```text
/api/internal/dungeonbuddy/v1/statblocks
```

with operation-specific child paths defined by the authoritative contract.

## 5. What should be reused

Reuse after wrapping behind explicit boundaries:

- internal API-key comparison;
- OpenAI Structured Outputs call mechanics;
- schema strictness lessons;
- prompt-domain knowledge and balance guidance;
- Firestore client and deployment credentials;
- Cloudflare-backed asset upload and URL handling;
- existing statblock fixtures as source material;
- combat-default derivation ideas as DungeonBuddy projection requirements;
- current deployment process and port.

Do not reuse as canonical v1 design:

- `StatBlockDetails`;
- `Action`;
- v2 draft envelope;
- Markdown as source;
- mutable statblock project documents;
- the monolithic statblock router;
- global service objects;
- current prompt examples verbatim;
- current normalization of random UUIDs into mutable JSON.

## 6. Roadmap policy

The implementation roadmap follows these rules:

1. Pure domain and contract behavior lands before provider or persistence code.
2. Every infrastructure component has an in-memory or fake implementation for tests.
3. Candidate generation and revision persistence are separate milestones.
4. The route is not declared usable until exact revision replay works.
5. DungeonBuddy consumes generated OpenAPI types rather than handwritten canonical DTOs.
6. No broad legacy migration is hidden inside a v1 route PR.
7. Old routes remain untouched until a post-launch cleanup explicitly addresses them.
8. Each PR produces a usable, tested successor seam.

## 7. Recommended PR ladder

The detailed roadmap and individual handoffs live in:

```text
Docs/Plans/PLAN-dungeonbuddy-statblock-v1-route-roadmap.md
Docs/Plans/HANDOFF-pr12-statblock-v1-bounded-context-foundation.md
Docs/Plans/HANDOFF-pr13-statblock-v1-contract-models-fixtures.md
Docs/Plans/HANDOFF-pr14-statblock-v1-canonicalization-validation-digest.md
Docs/Plans/HANDOFF-pr15-statblock-v1-repositories-persistence.md
Docs/Plans/HANDOFF-pr16-statblock-v1-structured-generation-service.md
Docs/Plans/HANDOFF-pr17-statblock-v1-candidate-api.md
Docs/Plans/HANDOFF-pr18-statblock-v1-revision-resource-api.md
Docs/Plans/HANDOFF-pr19-statblock-v1-assets-openapi-consumer-contract.md
Docs/Plans/HANDOFF-pr20-statblock-v1-production-hardening-launch.md
Docs/Plans/HANDOFF-pr21-statblock-legacy-quarantine-repo-hygiene.md
```

PR21 is post-launch and is not a gate for DungeonBuddy integration.

## 8. Audit acceptance

This audit is satisfied when the roadmap:

- creates no new v1 code inside the legacy monolithic router;
- keeps pure contract tests independent of the full app import;
- makes provider and persistence dependencies replaceable in tests;
- defines immutable revision persistence separately from project autosave;
- uses one canonical definition for Structured Outputs, API editing, and storage;
- preserves exact revision identity through reads;
- treats broad cleanup as explicit work rather than incidental refactoring.
