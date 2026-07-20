# HANDOFF — PR21 Legacy statblock quarantine and repository hygiene

**Status:** POST-LAUNCH — READY AFTER PR20  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessor:** PR20 production launch  
**Route impact:** no intended v1 behavior change

## PR20 predecessor completion notes

- PR20 launch commit: `feat(statblocks_v1): harden and launch-ready v1 route (PR20)`.
  The v1 contract artifact now has fingerprint `sha256:0d0969b8102e7ae83d1fafa6ed473505eec4fa87ae4f27adda256db4e891491c`;
  use the runbook/config guide before touching its route wiring.
- Generation can be disabled with `STATBLOCKS_V1_FEATURE_ENABLED=false` while
  exact persisted reads remain available. PR20 intentionally left every legacy
  route in place; PR21 owns consumer evidence, quarantine, and any cleanup.
- The current server has no Dockerfile. It uses `uv.lock` and should be built
  from that committed lockfile rather than a fresh dependency compilation.
- No legacy consumer inventory was collected during launch hardening. Treat
  every route listed below as active until production evidence says otherwise.

## 0. Mission

Reduce architectural ambiguity and repository drag after the DungeonBuddy statblock v1 route is operating.

This PR is intentionally post-launch. It must use real consumer evidence before removing or moving legacy behavior.

## 1. Consumer audit first

Before changing legacy routes, identify consumers of:

```text
/api/statblockgenerator/generate-statblock
/api/statblockgenerator/v2/generate-draft
/api/statblockgenerator/v2/render-draft
legacy project/session/image endpoints
```

Record:

- frontend/browser consumers;
- DungeonBuddy consumers, if any remain;
- production traffic evidence available;
- tests and documentation referring to each route;
- whether route is active, dormant, or safe to deprecate.

Do not infer “unused” from lack of recent code changes alone.

## 2. Router quarantine

The current statblock router mixes generation, v2 adaptation, validation, images, projects, and sessions.

Refactor only as supported by tests and consumer evidence. Possible shape:

```text
routers/statblock_legacy_generation_router.py
routers/statblock_legacy_projects_router.py
routers/statblock_legacy_assets_router.py
routers/statblock_v2_compatibility_router.py
```

or an equivalent clearly marked legacy package.

The goal is navigational clarity and reduced import coupling, not aesthetic file splitting.

The v1 router remains separate and must not gain dependencies on these modules.

## 3. Duplicate and misleading behavior

Address or document:

- duplicate `/health` declarations in the legacy router;
- health responses with inconsistent names/versions;
- optimistic image-deletion success after failures;
- direct sync Firestore calls inside async handlers;
- unused imports/global clients where removal is safe;
- endpoint docstrings that no longer describe actual auth or storage behavior;
- accepted-but-unimplemented v2 modes.

Behavioral fixes require tests and explicit release notes. Do not silently alter legacy response shapes.

## 4. Documentation authority

Mark active authority clearly:

```text
Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md
Docs/Design/AUDIT-dungeonbuddy-statblock-v1-route-readiness.md
Docs/Plans/PLAN-dungeonbuddy-statblock-v1-route-roadmap.md
```

Mark the v2 command-board design/audit/handoffs as historical or superseded for DungeonBuddy without deleting useful evidence.

Update README to accurately describe the server as its actual deployment shape—currently a modular FastAPI application within a larger multi-container product—not a collection of independently deployed backend microservices unless that is genuinely true at launch time.

## 5. Repository artifacts

Audit and remove or ignore generated/stale artifacts where safe, including examples such as:

- `dungeonmind.egg-info`;
- `.VSCodeCounter` outputs;
- obsolete generated requirements files;
- caches or local reports;
- duplicate historical progress reports with no authority marker.

Update `.gitignore` and document any artifacts intentionally retained.

Do not delete campaign/user data or deployment-required generated assets.

## 6. Dependency hygiene

Review `pyproject.toml`, `uv.lock`, and Docker installation.

Potential improvements:

- remove pytest from runtime dependencies and keep it in dev/test groups;
- use committed lockfile in Docker for reproducibility;
- separate heavy optional feature dependencies where practical;
- pin or vendor the git-based GenerationEngine dependency more reliably;
- ensure focused v1 tests do not install unrelated ML/image stacks;
- remove duplicate dev dependency declarations.

Do not perform a sweeping dependency upgrade in the same PR unless independently verified. Prefer structural grouping with unchanged resolved versions.

## 7. Application startup debt

Document or safely address:

- environment loading in `app.py` and Firebase modules;
- logging of environment values;
- global service construction;
- lifespan function defined but not wired;
- startup of Rules Lawyer embeddings;
- lack of a general application factory.

A full app-factory conversion may exceed this PR. If so, create a successor design/handoff rather than partially rewriting startup without tests.

## 8. Test architecture cleanup

Improve tests based on the working v1 pattern:

- avoid global production-app import for module-specific tests;
- create router/app fixtures by bounded context;
- use dependency overrides rather than monkeypatching global service instances;
- distinguish unit, isolated HTTP, infrastructure integration, and live smoke markers;
- document required commands;
- ensure no PR claims verification based only on `py_compile`.

Do not require all old tests to be repaired before making targeted improvements, but report remaining failures honestly.

## 9. Suggested outputs

```text
updated README.md
legacy router/package split where justified
updated .gitignore
cleaned generated artifacts
pyproject/Docker dependency cleanup
active/superseded doc markers
Docs/Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md
optional successor handoff for app factory/startup modernization
```

## 10. Testing requirements

- v1 full focused suite unchanged and passing;
- legacy route snapshot/smoke tests before and after any move;
- import/startup smoke;
- Docker build when dependency files change;
- active consumer route smoke;
- repository search confirms removed artifacts are ignored;
- docs links resolve.

## 11. Acceptance criteria

PR21 is complete when:

- new contributors/agents can identify v1 authority immediately;
- legacy routes are clearly named and still work for known consumers;
- duplicate/misleading health behavior is resolved or explicitly preserved with rationale;
- generated repository artifacts are removed/ignored where safe;
- dependency/test commands are more reproducible;
- broad remaining startup debt is documented rather than hidden;
- no v1 contract, digest, or revision behavior changes.

## 12. Non-goals

- no deletion of active legacy consumers;
- no rewrite into separate microservices;
- no database migration;
- no new statblock v1 feature;
- no mass dependency version upgrade;
- no unrelated frontend refactor.

## 13. Completion record

The PR description must include:

- consumer inventory;
- files moved/removed;
- compatibility evidence;
- dependency/build changes;
- tests actually run;
- remaining known architecture debt;
- recommended next modernization slice, if any.
