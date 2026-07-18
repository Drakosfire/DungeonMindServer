# Audit: Remaining DungeonMindServer Architecture Debt

**Status:** ACTIVE — post-PR21 follow-up inventory  
**Last reviewed:** 2026-07-17  
**Scope:** startup and application-composition debt intentionally outside the statblock v1 contract.

## Verified debt

1. `app.py` loads environment files and logs configuration at import time. It also logs the external SMS endpoint value; startup configuration should be centralized and sensitive values minimized.
2. `app.py` constructs `RulesLawyerService` globally. The declared `lifespan` function preloads embeddings but is not passed to `FastAPI(...)`, so its intended lifecycle behavior is currently unwired.
3. The application mounts unrelated product routers in one global module. Focused bounded-context tests avoid importing it, but production startup still couples unrelated dependencies and credentials.
4. Several legacy async route handlers call synchronous Firestore client methods directly. This can block the event loop under load.
5. Legacy StatBlockGenerator retains global service construction and synchronous Firestore access; PR21 only separated its historical v2 routes to clarify ownership without altering response behavior.
6. The server has no general application factory for isolated router composition, settings injection, or startup tests.

## Recommended successor slice

Create an application-factory/startup modernization PR that:

- introduces a typed settings object and explicit environment-loading boundary;
- wires a real FastAPI lifespan and moves Rules Lawyer preload behind a tested startup policy;
- composes routers through a factory with dependency injection;
- adds isolated startup tests and a production-startup smoke test;
- inventories and offloads blocking Firestore operations without changing legacy response contracts.

Do not combine that work with v1 contract evolution, legacy consumer removal, or dependency upgrades.
