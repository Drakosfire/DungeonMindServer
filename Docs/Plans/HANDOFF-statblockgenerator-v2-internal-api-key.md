# HANDOFF — Lock down StatBlockGenerator v2 endpoints with internal API key

**Created:** 2026-06-08  
**Updated:** 2026-06-08  
**Repo:** `Drakosfire/DungeonMindServer`  
**Target base branch:** `main`  
**Suggested next branch:** `codex/statblockgenerator-v2-internal-api-key`  
**Depends on:** PR #10 / `17ed495d7cebbff28c833788a5cccf3b3728eb53` — Add StatBlockGenerator v2 `render-draft` endpoint  
**Mode:** Security hardening handoff. Keep this slice narrow and do not change generator behavior.

---

## 0. Copyable task prompt

```markdown
You are implementing the next narrow security PR in `Drakosfire/DungeonMindServer`.

Read first:

`Docs/Plans/HANDOFF-statblockgenerator-v2-internal-api-key.md`

Goal: lock down the StatBlockGenerator v2 producer endpoints behind a simple internal service-to-service API key.

Protect only:

- `GET /api/statblockgenerator/v2/health`
- `POST /api/statblockgenerator/v2/generate-draft`
- `POST /api/statblockgenerator/v2/render-draft`

Do not change generator behavior, markdown rendering, combat defaults, provenance, the v2 response envelopes, user OAuth, Firestore persistence, or the legacy app-facing `/api/statblockgenerator/generate-statblock` endpoint.

Preferred contract:

- Header: `X-DungeonBuddy-Internal-Key`
- Server env var: `DUNGEONBUDDY_INTERNAL_API_KEY`

Implement a small reusable FastAPI dependency, attach it to the v2 routes, and add focused route tests for missing/wrong/correct key behavior. Missing or wrong keys must not call generation or rendering logic. Never log the provided or expected secret.
```

---

## 1. Re-anchor

DungeonMindServer is internet-reachable. The new StatBlockGenerator v2 producer endpoints are intended for internal product consumers such as DungeonBuddy, not public anonymous callers.

Current v2 endpoints:

```text
GET  /api/statblockgenerator/v2/health
POST /api/statblockgenerator/v2/generate-draft
POST /api/statblockgenerator/v2/render-draft
```

These endpoints should be locked down before DungeonBuddy treats them as a durable product dependency.

I searched for an existing internal API-key pattern using terms like `internal api key`, `X-API-Key`, `API_KEY`, `Header`, and `Depends`. I found the existing OAuth/session user auth path in `routers/auth_router.py`, but did not find a reusable service-to-service internal API-key dependency. If one exists under a different naming convention, prefer reusing it.

---

## 2. PR goal

Add a small internal service-to-service authentication dependency for StatBlockGenerator v2 endpoints.

The intended runtime shape:

```text
DungeonBuddy backend/proxy
→ sends internal API key header
→ DungeonMindServer validates key
→ v2 StatBlockGenerator route executes
```

The browser should never receive or send this key directly.

---

## 3. Design position

This PR is a **shared-secret gate**, not a full auth redesign.

The goal is to prevent anonymous internet callers from using internal producer endpoints while preserving the product architecture:

```text
DungeonBuddy frontend
→ DungeonBuddy backend/proxy
→ DungeonMindServer v2 producer endpoint
```

This keeps service credentials server-side and avoids binding browser code directly to DungeonMindServer.

---

## 4. Recommended auth shape

Use a simple header-based shared secret for this first hardening slice.

Suggested header:

```text
X-DungeonBuddy-Internal-Key: <secret>
```

Suggested env var on DungeonMindServer:

```text
DUNGEONBUDDY_INTERNAL_API_KEY=<secret>
```

Alternative names are acceptable if the repo already has conventions, but the chosen names must be documented in the PR and tests.

Behavior:

- If the expected env var is missing in production-like environments, protected v2 routes should fail closed or clearly report server misconfiguration.
- If the header is missing or wrong, return `401 Unauthorized` or `403 Forbidden` with a generic error.
- Do not log the provided key.
- Do not log the expected key.
- Do not include either key in exception details.
- Do not protect legacy app-facing routes in this PR unless intentionally chosen and documented.

Recommended status codes:

| Case | Status | Body guidance |
|---|---:|---|
| Missing header | 401 | Generic `Unauthorized` / `Missing internal API key` |
| Wrong header | 403 | Generic `Forbidden` / `Invalid internal API key` |
| Missing server env in production-like env | 500 | Generic `Internal API key is not configured` |
| Correct header | pass-through | Existing v2 behavior unchanged |

Use constant-time comparison, for example `secrets.compare_digest`, rather than direct string equality.

---

## 5. Scope

Protect these v2 routes:

```text
GET  /api/statblockgenerator/v2/health
POST /api/statblockgenerator/v2/generate-draft
POST /api/statblockgenerator/v2/render-draft
```

Keep existing app-facing endpoint behavior unchanged:

```text
POST /api/statblockgenerator/generate-statblock
```

The existing endpoint can be revisited separately if needed. This PR is about the new internal producer contract.

---

## 6. Suggested implementation shape

Likely files:

```text
routers/internal_auth.py
routers/statblockgenerator_router.py
tests/statblockgenerator/test_statblockgenerator_v2_auth.py
```

or, if preferred:

```text
auth_service.py
routers/statblockgenerator_router.py
tests/statblockgenerator/test_statblockgenerator_v2_auth.py
```

Prefer a small reusable dependency, for example:

```python
import os
import secrets
from fastapi import Header, HTTPException

INTERNAL_KEY_HEADER = "X-DungeonBuddy-Internal-Key"
INTERNAL_KEY_ENV = "DUNGEONBUDDY_INTERNAL_API_KEY"

async def require_dungeonbuddy_internal_key(
    x_dungeonbuddy_internal_key: str | None = Header(default=None, alias=INTERNAL_KEY_HEADER),
) -> None:
    expected = os.getenv(INTERNAL_KEY_ENV)
    if not expected:
        raise HTTPException(status_code=500, detail="Internal API key is not configured")
    if not x_dungeonbuddy_internal_key:
        raise HTTPException(status_code=401, detail="Missing internal API key")
    if not secrets.compare_digest(x_dungeonbuddy_internal_key, expected):
        raise HTTPException(status_code=403, detail="Invalid internal API key")
```

Then attach it only to v2 routes, route-by-route:

```python
@router.get("/v2/health", dependencies=[Depends(require_dungeonbuddy_internal_key)])
```

or through a sub-router if the code structure makes that cleaner.

Route-by-route is acceptable and probably the smallest safe change.

---

## 7. Environment behavior

Decide and document the dev behavior explicitly.

Recommended for this PR:

- Require `DUNGEONBUDDY_INTERNAL_API_KEY` in all environments where the protected routes are called.
- Tests monkeypatch this env var.
- Local developers can set it in `.env`.

Avoid adding a dev bypass unless there is strong local workflow friction.

If a bypass is added anyway:

```text
ALLOW_UNAUTHENTICATED_INTERNAL_ROUTES=true
```

then it must:

- default to safe behavior;
- never be enabled silently in production-like environments;
- log a warning when active;
- be tested.

The simplest and preferred path is **no bypass**.

---

## 8. Test expectations

Add focused tests; no OpenAI calls.

Minimum tests:

1. **Missing header denied**
   - `GET /api/statblockgenerator/v2/health` returns `401` without the header.

2. **Wrong header denied**
   - `GET /api/statblockgenerator/v2/health` returns `403` with an incorrect key.

3. **Correct header accepted**
   - `GET /api/statblockgenerator/v2/health` returns `200` with the correct key.

4. **Missing server env fails closed**
   - unset `DUNGEONBUDDY_INTERNAL_API_KEY` and assert protected v2 route returns `500` or the chosen misconfiguration response.

5. **Generate route protected before generation**
   - missing/wrong key does not call `generate_creature()`.
   - correct key reaches existing mocked `generate-draft` behavior.

6. **Render route protected before adapter success**
   - missing/wrong key does not return a rendered draft.
   - correct key reaches existing `render-draft` behavior.

7. **Legacy route unchanged**
   - this PR does not add the internal-key dependency to `/api/statblockgenerator/generate-statblock`.
   - Test this with either route inspection or a mocked legacy request, whichever is lowest friction.

Use `monkeypatch.setenv` / `monkeypatch.delenv` for secrets. Do not require real secrets in tests.

Suggested test file:

```text
tests/statblockgenerator/test_statblockgenerator_v2_auth.py
```

Suggested focused command:

```text
python -m pytest tests/statblockgenerator/test_statblockgenerator_v2_auth.py -v
```

If dependency/environment issues block pytest, at minimum run static compile and document the blocker in the PR description, but still write the tests.

---

## 9. DungeonBuddy coordination

DungeonBuddy's proxy/client seam should inject the internal key server-side only.

Expected Buddy-side env/config:

```text
DUNGEONMIND_SERVER_URL=<server url>
DUNGEONMIND_INTERNAL_API_KEY=<same secret or configured secret reference>
```

The frontend should call Buddy's own API/proxy. It should not call DungeonMindServer directly and should never receive the internal key.

This has already been added to the Buddy-side consumer seam handoff:

```text
Drakosfire/DungeonMindBuddy/Docs/Plans/HANDOFF-dungeonbuddy-statblockgenerator-proxy-client.md
```

---

## 10. Out of scope

Do not redesign user OAuth.

Do not add database-backed API key management.

Do not build key rotation UI.

Do not add per-user permissions to StatBlockGenerator v2.

Do not change generation, rendering, markdown, combat defaults, warning, or provenance behavior.

Do not add DungeonBuddy code in this PR.

Do not expose secrets in frontend code, logs, exception details, fixtures, or docs.

---

## 11. Acceptance criteria

The PR is ready when:

- StatBlockGenerator v2 health/generate/render routes require an internal API key;
- the required key is read from documented environment config;
- key comparison uses a safe comparison method such as `secrets.compare_digest`;
- missing/wrong keys are rejected with stable status codes;
- missing server config fails closed with a generic error;
- correct key allows the existing v2 behavior through;
- tests cover accepted and rejected cases without OpenAI calls;
- protected-route tests prove generation is not called when auth fails;
- the internal key is never logged;
- legacy app-facing routes remain unchanged unless explicitly documented.

---

## 12. Suggested PR description

```markdown
### Motivation

DungeonMindServer is internet-reachable, and the StatBlockGenerator v2 producer endpoints are intended for internal consumers such as DungeonBuddy. This PR locks those v2 endpoints behind a simple internal service-to-service API key before Buddy builds against them as a product dependency.

### Description

- Added a reusable internal API-key dependency for service-to-service routes.
- Protected `GET /api/statblockgenerator/v2/health`, `POST /api/statblockgenerator/v2/generate-draft`, and `POST /api/statblockgenerator/v2/render-draft`.
- Read the expected key from `DUNGEONBUDDY_INTERNAL_API_KEY`.
- Validated the `X-DungeonBuddy-Internal-Key` header with constant-time comparison.
- Added tests for missing, wrong, missing-config, and correct key behavior.
- Confirmed legacy app-facing StatBlockGenerator routes remain unchanged.

### Testing

- `python -m pytest tests/statblockgenerator/test_statblockgenerator_v2_auth.py -v`
```

---

## 13. Review checklist

When reviewing the PR, confirm:

- [ ] v2 routes are actually protected.
- [ ] legacy route is not unintentionally protected.
- [ ] missing key fails.
- [ ] wrong key fails.
- [ ] missing env fails closed.
- [ ] correct key passes.
- [ ] `generate_creature()` is not called when auth fails.
- [ ] `render-draft` does not return a draft when auth fails.
- [ ] secrets are not logged or returned.
- [ ] tests do not require real secrets or OpenAI.
