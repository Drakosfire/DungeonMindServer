# Report — DungeonMindServer Documentation Authority Audit, 2026-09-25

**Status:** COMPLETE — first rigor pass  
**Repository:** `Drakosfire/DungeonMindServer`  
**Cross-repository owner model:** DungeonOverMind repository ownership / platform-refresh stewardship

## Result

DungeonMindServer documentation now reflects the repository's actual job:

> **public DungeonMind Web API / BFF implemented as a modular FastAPI monolith**

This repository owns backend/product implementation truth. Cross-repository architecture, ownership, and sequencing stay in DungeonOverMind.

## What changed

### Current authority indexes

Added:

- `Docs/README.md` — repository documentation authority/placement index;
- `Docs/Design/README.md` — current design authority index;
- `Docs/Plans/README.md` — active-plan boundary.

Rewrote root `README.md` around the actual Web API/BFF role rather than legacy “microservices showcase” framing.

### Completed statblock transition archived

Moved 18 completed/superseded plan/design files from active context into:

`Docs/Archive/2026-09-25/`

This includes:

- PR12–PR26 statblock-v1 implementation handoffs;
- the original PR12–PR21 route roadmap;
- predecessor v2 command-board handoffs/audit;
- original v1 readiness audit.

GitHub PR truth was reconciled before archival. PR12–PR26 are merged. PR27 merged only to a divergent feature branch; PR28 and PR29 remain open/divergent and are **not** treated as current `main` authority.

### Active Server docs revalidated

The current architecture-debt audit was refreshed against main. Current verified pressure includes:

- import-time environment/config/router composition;
- an unwired FastAPI lifespan;
- globally constructed RulesLawyer / legacy statblock services;
- `create_app()` returning the already-constructed global app rather than a fresh app factory;
- in-process `EnhancedGlobalSessionManager` state;
- legacy synchronous persistence risk in async paths;
- Docker dependency installation that resolves from `pyproject.toml` instead of the committed `uv.lock`.

The statblock-v1 runbook was corrected: a Dockerfile now exists, but its image build is not lockfile-reproducible.

### RulesLawyer docs corrected

The old root `README_MODEL_DOWNLOAD.md` described a removed compose/volume/`TRANSFORMERS_CACHE` deployment contract and a model-directory layout that no longer matches the current loader.

It is archived. Current model-cache truth now lives in `ruleslawyer/README_DATA_FILES.md`, based on the actual loader precedence:

```text
EMBEDDING_MODEL_PATH
→ HF_HOME
→ HUGGINGFACE_HUB_CACHE
→ SENTENCE_TRANSFORMERS_HOME
→ ~/.cache/huggingface
```

## Active central documentation shape

Final first-pass shape:

```text
71 files under Docs/
23 historical Archive files
48 active files
36 active executable/design fixtures
12 active prose/index/config/runbook/report files
```

The increase from the working census is intentional: the cleanup added authority indexes, this durable audit report, and the dated archive ledger while removing stale material from active context.

The 36 fixtures are intentionally active because tests/smokes consume them or they are current contract/evaluation evidence. They are not treated as prose-documentation clutter.

Active prose authority is intentionally small:

- Server architecture-debt audit;
- legacy statblock consumer inventory;
- canonical DungeonBuddy statblock-v1 design;
- legacy→v1 field disposition;
- GenerationEngine structured-conformance consumer guidance;
- Design index;
- statblock-v1 configuration;
- platform-refresh local anchor;
- Plans index;
- Docs index;
- statblock-v1 operational runbook.

## Deliberate non-cleanup

### Open statblock PR leases

PR28 modifies the current v1 fixture packs and generated contract artifacts. PR29 modifies statblock domain code. Those paths were left untouched.

### Executable fixture paths

The historical command-board fixture directory remains in place because current tests import it directly. Moving it would be a code/test refactor, not documentation cleanup.

### Colocated module documentation

Module-local docs remain where they are when they describe behavior owned by that module, e.g.:

- `ruleslawyer/README_DATA_FILES.md`;
- `cardgenerator/docs/MEMORY_ONLY_APPROACH.md`;
- `tests/statblockgenerator/README.md`;
- `static/fonts/README.md`.

They should be retired only after checking current code/test truth, not centralized for aesthetic consistency.

## Placement rule going forward

```text
current backend implementation/design
→ DungeonMindServer

frontend behavior
→ LandingPage

reusable inference mechanics
→ GenerationEngine

durable world-knowledge internals
→ DungeonMind

Buddy product/orchestration
→ DungeonMindBuddy

cross-repo ownership/contracts/sequencing
→ DungeonOverMind
```

Within Server:

```text
current code/tests/schema
→ active owner design/config/runbook
→ merged PR evidence
→ Archive / Git history
```

Open/stacked PRs are proposals, not current-main documentation authority.

This rule is executable: `tests/statblockgenerator/test_production_app_mount_smoke.py::test_current_authority_docs_exist` now asserts the current authority set instead of requiring archived PR21-era plans/audits.

## Current cross-repository pressure

The active local platform-refresh anchor remains:

`Docs/Plans/ANCHOR-dungeonmind-net-platform-refresh.md`

It authorizes no code by itself. DungeonOverMind owns the cross-repository reconnaissance/sequence; implementation enters this repository only through bounded Server handoffs.
