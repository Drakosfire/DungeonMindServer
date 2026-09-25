# Audit: Remaining DungeonMindServer Architecture Debt

**Status:** ACTIVE — revalidated against `main` 2026-09-25  
**Repository anchor:** current main at audit refresh descended from `4d3c96668425db40af95e1850a20d43cd1baa74d`  
**Scope:** application composition, lifecycle, persistence/runtime efficiency, and deployment debt outside bounded feature contracts.  
**Cross-repository steward:** DungeonOverMind platform-refresh lane.

## Verified current debt

1. **Environment/configuration work still happens at import time.**
   `app.py` chooses an environment and calls `load_dotenv(..., override=True)` before importing many routers. Secret values are no longer logged directly in the inspected startup block; presence-only SMS/Twilio checks are debug-level.

2. **The declared FastAPI lifespan is not wired.**
   `app.py` defines `lifespan(app)` to preload RulesLawyer embeddings, but production constructs `app = FastAPI()` rather than `FastAPI(lifespan=lifespan)`. `RulesLawyerService` is still created globally.

3. **Router composition remains import-time/global.**
   Unrelated feature routers and several infrastructure dependencies are imported and mounted in one module. This is a valid modular-monolith deployment shape, but it makes startup/tests sensitive to unrelated dependencies and credentials.

4. **`create_app()` is not yet an isolated application factory.**
   A `create_app() -> FastAPI` function now exists and is useful to tests, but it returns the already-constructed module-global `app`. It does not provide fresh settings injection, selective router composition, or isolated lifecycle construction.

5. **Legacy StatBlockGenerator remains process-global.**
   The legacy app router and v2 compatibility router deliberately share one `StatBlockGenerator` / OpenAI client through `statblockgenerator.runtime.get_statblock_generator()`. This avoids duplicate clients but remains global lifecycle state.

6. **Blocking persistence remains a risk in legacy async paths.**
   The v1 bounded context explicitly offloads synchronous repository operations where needed. Legacy Firestore-backed routes still require a focused inventory before claiming the event loop is free of synchronous I/O.

7. **Global tool/session state is process memory.**
   `EnhancedGlobalSessionManager` owns a Python `dict` of sessions in-process. Restart/multi-worker semantics therefore cannot be treated as durable product authority. The platform-refresh steward is explicitly evaluating this boundary.

8. **The Docker build is not lockfile-reproducible.**
   A Dockerfile now exists, but it copies only `pyproject.toml`, runs `uv pip compile ... pyproject.toml`, and installs the freshly compiled requirements. It does not consume the committed `uv.lock`. Local `uv sync --locked` and image dependency resolution can therefore drift.

## Current modernization direction

Do not rewrite the server into microservices by default.

The current platform-refresh reconnaissance should decide bounded slices around:

- explicit typed/global settings and environment-loading boundary;
- real FastAPI lifespan wiring;
- genuinely fresh application factory / tested composition seams where useful;
- durable authority for product-critical session/account/world state;
- measured removal/offload of blocking synchronous I/O;
- reproducible Docker installation from the committed lock;
- cleanup of compatibility routers only with current consumer evidence.

## Scope guard

Do not combine these concerns into statblock-v1 contract evolution.

The statblock bounded context remains useful evidence for how to isolate domain/application/infrastructure/API layers inside the modular monolith. Platform-wide modernization should reuse that lesson without forcing every legacy module into the same shape in one rewrite.
