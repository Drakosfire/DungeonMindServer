# HANDOFF — Lock down StatBlockGenerator v2 endpoints with internal API key

**Created:** 2026-06-08  
**Repo:** `Drakosfire/DungeonMindServer`  
**Target base branch:** `main`  
**Suggested next branch:** `codex/statblockgenerator-v2-internal-api-key`  
**Depends on:** PR #10 / `17ed495d7cebbff28c833788a5cccf3b3728eb53` — Add StatBlockGenerator v2 `render-draft` endpoint  
**Mode:** Security hardening handoff. Keep this slice narrow and do not change generator behavior.

---

## 0. Re-anchor

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

## 1. PR goal

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

## 2. Recommended auth shape

Use a simple header-based shared secret for this first hardening slice.

Suggested header:

```text
X-DungeonBuddy-Internal-Key: <secret>
```

Suggested env var on DungeonMindServer:

```text
DUNGEONBUDDY_INTERNAL_API_KEY=<secret>
```

Alternative names are fine if the repo already has conventions. Keep the chosen names documented in the PR.

Behavior:

- If the expected env var is missing in production-like environments, v2 protected routes should fail closed or clearly report misconfiguration.
- If the header is missing or wrong, return `401` or `403` with a generic error.
- Do not log the provided key or expected key.
- Do not protect legacy app-facing routes in this PR unless intentionally chosen.

---

## 3. Scope

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

## 4. Suggested implementation shape

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

The dependency should be boring and reusable:

```python
async def require_internal_api_key(request: Request) -> None:
    ...
```

or:

```python
async def require_dungeonbuddy_internal_key(x_key: str | None = Header(default=None)) -> None:
    ...
```

Then attach it only to v2 routes, either route-by-route:

```python
@router.post("/v2/generate-draft", dependencies=[Depends(require_internal_api_key)])
```

or through a sub-router if that is cleaner.

---

## 5. Environment behavior

Decide and document the dev behavior explicitly.

Recommended:

- In `production` / deployed environments, missing `DUNGEONBUDDY_INTERNAL_API_KEY` is a server misconfiguration and should fail closed.
- In local development, allow either:
  - a local key in `.env`; or
  - an explicit bypass flag such as `ALLOW_UNAUTHENTICATED_INTERNAL_ROUTES=true`.

If a bypass flag is added, it must default to safe behavior and should log a warning when active.

Do not make silent unauthenticated access the default for internet-deployed environments.

---

## 6. Test expectations

Add focused tests; no OpenAI calls.

Minimum tests:

1. **Missing header denied**
   - v2 health returns 401/403 without the header.

2. **Wrong header denied**
   - v2 health returns 401/403 with an incorrect key.

3. **Correct header accepted**
   - v2 health returns 200 with correct key.

4. **Generate route protected before generation**
   - missing/wrong key does not call `generate_creature()`.

5. **Render route protected**
   - missing/wrong key does not call adapter logic.

6. **Legacy route unchanged**
   - existing `/api/statblockgenerator/generate-statblock` behavior is not changed by this PR, unless intentionally documented.

Use monkeypatch/env fixtures to set the expected key. Do not require real secrets in tests.

---

## 7. DungeonBuddy coordination

DungeonBuddy's proxy/client seam should inject the internal key server-side only.

Expected Buddy-side env/config:

```text
DUNGEONMIND_SERVER_URL=<server url>
DUNGEONMIND_INTERNAL_API_KEY=<same secret or configured secret reference>
```

The frontend should call Buddy's own API/proxy. It should not call DungeonMindServer directly and should never receive the internal key.

---

## 8. Out of scope

Do not redesign user OAuth.

Do not add database-backed API key management.

Do not build key rotation UI.

Do not add per-user permissions to StatBlockGenerator v2.

Do not change generation, rendering, markdown, combat defaults, warning, or provenance behavior.

Do not add DungeonBuddy code in this PR.

---

## 9. Acceptance criteria

The PR is ready when:

- StatBlockGenerator v2 health/generate/render routes require an internal API key;
- the required key is read from documented environment config;
- missing/wrong keys are rejected with stable status codes;
- correct key allows the existing v2 behavior through;
- tests cover accepted and rejected cases without OpenAI calls;
- the internal key is never logged;
- legacy app-facing routes remain unchanged unless explicitly documented.

---

## 10. Suggested PR description

```markdown
### Motivation

DungeonMindServer is internet-reachable, and the StatBlockGenerator v2 producer endpoints are intended for internal consumers such as DungeonBuddy. This PR locks those v2 endpoints behind a simple internal service-to-service API key before Buddy builds against them as a product dependency.

### Description

- Added a reusable internal API-key dependency for service-to-service routes.
- Protected `GET /api/statblockgenerator/v2/health`, `POST /api/statblockgenerator/v2/generate-draft`, and `POST /api/statblockgenerator/v2/render-draft`.
- Read the expected key from documented environment config.
- Added tests for missing, wrong, and correct key behavior.
- Confirmed legacy app-facing StatBlockGenerator routes remain unchanged.

### Testing

- `<repo-appropriate focused pytest command>`
```
