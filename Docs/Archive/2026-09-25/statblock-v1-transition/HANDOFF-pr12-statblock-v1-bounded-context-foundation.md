# HANDOFF — PR12 Statblock v1 bounded-context foundation

**Status:** READY  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Target branch:** new feature branch from `main`  
**Predecessor:** `Docs/Plans/PLAN-dungeonbuddy-statblock-v1-route-roadmap.md`  
**Successor:** `HANDOFF-pr13-statblock-v1-contract-models-fixtures.md`

## 0. Mission

Create a clean, independently testable bounded context for the DungeonBuddy statblock v1 contract before implementing its detailed schema or real behavior.

This PR is an architectural foundation. It must prove that future statblock v1 domain and route tests can run without importing the complete production app or requiring Firebase, OpenAI, Cloudflare, Rules Lawyer embeddings, or GenerationEngine.

## 1. Required architecture

Create a package with explicit dependency direction, tentatively:

```text
statblocks_v1/
  __init__.py
  domain/
    __init__.py
    errors.py
    protocols.py
  application/
    __init__.py
  infrastructure/
    __init__.py
  api/
    __init__.py
    dependencies.py
    router.py
```

Exact naming may change, but preserve:

```text
domain → standard library and Pydantic only
application → domain
infrastructure → domain/application plus external SDKs
api → domain/application and FastAPI
legacy statblockgenerator → no import into domain
```

## 2. Deliverables

### 2.1 Foundation router

Add a dedicated router mounted under:

```text
/api/internal/dungeonbuddy/v1
```

Expose only a health/capability endpoint such as:

```text
GET /api/internal/dungeonbuddy/v1/statblocks/health
```

It should return:

```json
{
  "status": "foundation",
  "contract": "dungeonmind.dungeonbuddy-statblocks",
  "contract_version": "1.0.0",
  "capabilities": []
}
```

Do not advertise generation, validation, or persistence yet.

### 2.2 Dependency seams

Define narrow protocols or dependency contracts for later work:

- generation provider;
- candidate repository;
- statblock repository;
- revision repository;
- asset gateway;
- ID allocator;
- clock.

These may initially contain minimal methods or placeholders, but they must not import concrete infrastructure.

### 2.3 Isolated test app

Provide a test helper that constructs a FastAPI application containing only the v1 router.

Tests must run without importing `app.py`.

### 2.4 Authentication

Reuse the current internal-key comparison behavior through a router-level dependency or a small v1 wrapper.

Do not copy authentication checks into every endpoint.

Map failures through a preliminary typed error response without exposing the expected key or configuration internals.

### 2.5 Focused verification lane

Add a reproducible command or CI job for the v1 package that does not require the full server’s external credentials or model downloads.

A minimal temporary dependency installation is acceptable if documented, but the PR must not claim that the full repository test environment is repaired.

## 3. Architecture critique to preserve

Do not:

- add v1 routes to `routers/statblockgenerator_router.py`;
- import `firestore.firebase_config` in the new router;
- construct OpenAI clients at module import;
- instantiate a global generator;
- reuse `StatBlockDetails` as a placeholder contract;
- import the full production app in focused tests;
- fix unrelated Rules Lawyer lifecycle behavior;
- reorganize all existing routers.

## 4. Suggested files

```text
statblocks_v1/domain/errors.py
statblocks_v1/domain/protocols.py
statblocks_v1/api/dependencies.py
statblocks_v1/api/router.py
tests/statblocks_v1/conftest.py
tests/statblocks_v1/test_health.py
app.py  # registration only, if safe
pyproject.toml or CI config  # focused test lane only
```

If registering the router in `app.py` triggers unrelated test coupling, keep route tests isolated while still wiring production registration narrowly.

## 5. Testing requirements

Required:

- domain package import succeeds with no external environment variables;
- isolated router health returns contract name/version;
- missing, wrong, and correct internal key behavior is tested;
- test confirms no Firebase/OpenAI provider is constructed;
- focused test command exits successfully from a clean environment.

Required focused command (import-isolated and dependency-isolated):

```bash
./scripts/run_statblocks_v1_tests.sh
```

Equivalent expanded form:

```bash
PYTHONPATH=. uv run --isolated --no-project \
  --with 'pytest>=8.3.5' --with 'fastapi>=0.115.4' \
  --with 'pydantic>=2.0' --with 'httpx>=0.27.0' \
  pytest --confcutdir=tests/statblocks_v1 tests/statblocks_v1 -q
```

`--confcutdir` cuts off ancestor `tests/conftest.py` (which imports production `app`).
`--isolated --no-project` skips the project `.venv` and the root server dependency
graph (OpenAI, Firebase, sentence-transformers, generationengine, …), installing
only pytest/FastAPI/Pydantic/HTTPX via `--with`.

The exact command must be recorded in the PR. Do not advertise `uv run pytest`
against the project environment as the focused lane.

## 6. Acceptance criteria

PR12 is complete when:

- the new package boundary exists;
- dependency direction is documented and enforced by imports/tests;
- the health stub is reachable through an isolated app;
- authentication is router-level;
- no legacy statblock type is presented as v1;
- tests run rather than merely compile;
- the successor can add contract models without touching legacy routing or infrastructure.

## 7. Non-goals

- no complete statblock schema;
- no OpenAI calls;
- no Firestore reads/writes;
- no candidate IDs;
- no revisions;
- no asset behavior;
- no legacy route migration;
- no broad dependency modernization.

## 8. Successor handoff

Before merge, update PR13’s handoff with:

- actual package paths;
- import rules;
- router factory/dependency override pattern;
- focused test command;
- any unavoidable production-app registration coupling.
