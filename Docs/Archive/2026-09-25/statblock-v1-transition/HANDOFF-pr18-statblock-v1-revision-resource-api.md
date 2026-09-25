# HANDOFF — PR18 Statblock v1 revision resource API

**Status:** IN REVIEW — rebased onto merged PR17; acceptance trust boundaries sealed  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessors:** PR14 trust core, PR15 repositories, PR17 router/error boundary  
**Successor:** `HANDOFF-pr19-statblock-v1-assets-openapi-consumer-contract.md`

## PR17 predecessor completion notes

- The v1 route prefix is `/api/internal/dungeonbuddy/v1`; all routes use
  `require_internal_service_auth` and the `X-DungeonBuddy-Internal-Key` shared key.
- Errors use top-level `{ "error": { "code", "message", "details"? } }` via the
  existing `StatblockV1HTTPError` / `register_error_handlers` seam. Request
  validation is path-scoped: only v1 paths get the typed envelope; legacy routes
  keep FastAPI `{"detail": ...}`.
- Generation failure kinds from final PR16 map explicitly (`ruleset_mismatch`,
  `source_digest_mismatch`, `invalid_request`, `revision_not_found`,
  `statblock_not_found`, `persistence_unavailable` → 503, provider outcomes).
  Unknown kinds fail closed as `500 generation_failed`, never a false
  `provider_unavailable`.
- Revision uses `ExactRevisionLocatorV1(statblock_id, revision_id)`. Production
  wiring in `app.py` injects `PersistenceDefinitionResolver` over
  `FirestoreStatblockPersistenceRepository`. Exactly one of `source_definition` /
  `source_locator` is enforced on the request DTO (422 `invalid_request`).
- Candidate generate/revise treat `request_id` as correlation/receipt metadata
  only. **Candidate idempotency is deferred** (not implemented) so PR15
  statblock/revision idempotency outcomes remain untouched. Do not assume
  request-id replay for candidates.
- Candidate lookup is `CandidateRepository.get(candidate_id, now=...)`; acceptance
  uses `get_for_acceptance` (ignores workflow expiry, still 404 when missing).
  Async routes call synchronous repositories through `asyncio.to_thread`.
- OpenAPI operations: `generate_statblock_candidate_v1`,
  `revise_statblock_candidate_v1`, `validate_statblock_definition_v1`,
  `get_statblock_candidate_v1`. ErrorEnvelopeV1 is declared on failure statuses.
  No accepted-resource routes existed yet before PR18.
- Tests override `get_generation_service`, `get_candidate_repository`,
  `get_persistence_repository`, `get_revision_service`, and `get_clock`.

## 0. Mission

Expose authoritative logical-statblock and immutable-revision resources through the DungeonBuddy v1 router.

This PR is the trust milestone: after it lands, DungeonBuddy may accept a reviewed definition and receive an exact durable revision locator suitable for Threat bindings, Plan/scene placement, and combat pinning.

## 1. Routes

Implement:

```text
POST /api/internal/dungeonbuddy/v1/statblocks
POST /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{revision_id}
```

Optional only if required by pagination design:

```text
GET /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions?cursor=...
```

Do not add mutation or deletion routes for accepted revisions.

## 2. Create logical statblock

Request should include:

```text
idempotency_key
complete StatblockDefinitionV1
optional candidate_id
change summary
accepted-through caller/actor provenance
optional asset bindings
```

Flow:

```text
resolve candidate provenance when supplied
→ validate submitted definition in persistence mode
→ canonicalize and digest again
→ create logical statblock + first revision atomically
→ return StatblockResourceV1 and StatblockRevisionResourceV1
```

The submitted definition may differ from the generated candidate because DungeonBuddy review permits editing. Record both source candidate and accepted definition digest in provenance when applicable.

## 3. Append revision

Request should include:

```text
idempotency_key
parent_revision_id
complete StatblockDefinitionV1
optional candidate_id
change summary
accepted-through provenance
optional asset bindings
```

DungeonMindServer validates and canonicalizes again. Do not trust a prior validation receipt supplied by DungeonBuddy.

## 4. Read behavior

### Logical statblock read

Returns stable identity and chronological latest revision metadata. It does not select a campaign-preferred revision.

### Revision list

Returns immutable revision metadata in a documented deterministic order. Support bounded pagination if the repository contract requires it.

### Exact revision read

Must resolve only the supplied `statblock_id + revision_id`.

It must never silently return latest, preferred, or parent revision.

## 5. Replay invariant

A revision returned immediately after create/append and the same revision returned later must have:

- identical canonical definition;
- identical definition digest;
- identical revision/statblock IDs;
- identical validation receipt content except fields that were never mutable;
- identical provenance and asset bindings;
- no dependency on current prompt, model, renderer, or latest revision.

Candidate-linked acceptance must also replay after the source candidate document is
gone (TTL deletion). Idempotency is consulted **before** `get_for_acceptance`, and
server-owned `provenance.candidate` audit evidence is excluded from the request
digest (`candidate_id` remains in the digest).

Idempotency is also consulted **before** semantic persistence validation.
Validation and candidate lookup run only when the key is genuinely new, so a
changed-but-invalid retry yields `409 idempotency_conflict` rather than
`422 validation_failed`, and exact replay survives future validator-policy
changes.

Add a full exact-replay test.

## 6. Idempotency

All write routes require idempotency keys.

Required behavior:

```text
same key + same canonical request
  → return original resource outcome
    (consult idempotency before persistence validation)

same key + changed definition, parent, or operation metadata
  → 409 typed idempotency conflict
    (even when the changed payload would fail persistence validation)

concurrent same-key requests
  → one revision only
```

No client-supplied revision ID.

## 7. Candidate provenance

When `candidate_id` is supplied:

- load the server-owned candidate via `get_for_acceptance`;
- reject missing candidates with `404 candidate_not_found` on first write;
- record source candidate ID, source definition digest, generation receipt
  locator/snapshot, and whether accepted definition changed under
  `provenance.candidate` (server-owned; never caller-supplied);
- never replace the submitted accepted definition with candidate content;
- never accept a free-form caller `provenance` object on the public DTO.

Expired candidates may still be accepted while their record remains available.
Workflow candidate GET returns `410` once expired. After TTL deletes the record,
same-key acceptance replay returns the original revision without requiring the
candidate document.

`actor` is acceptance provenance (`accepted_by`) only. Logical-statblock
`created_by` is the authenticated service identity (`dungeonbuddy`), not the
caller-asserted actor.

## 8. Validation failures

Persistence-mode errors block create/append.

Warnings may be accepted only when policy marks the definition persistence-ready. Return the full validation receipt in both success and validation failure envelopes so DungeonBuddy can present actionable issues.

## 9. Assets and digest

Asset bindings live in the revision envelope unless the authoritative contract explicitly places mechanics-relevant assets inside the definition.

Changing or adding art must not change the mechanics digest.

This PR may support typed asset locators supplied by the caller, while PR19 completes asset-gateway integration.

## 10. Authorization

Use router-level service authentication and caller context.

The v1 server-to-server route authorizes DungeonBuddy as a service. Actor/user information supplied for provenance is data, not proof of identity, unless a stronger trusted-user assertion mechanism is explicitly implemented.

Do not conflate service authentication with end-user ownership.

## 11. Suggested files

```text
statblocks_v1/application/revisions.py
statblocks_v1/api/resource_models.py
statblocks_v1/api/router.py
statblocks_v1/api/error_mapping.py
tests/statblocks_v1/api/test_statblock_resource_routes.py
tests/statblocks_v1/api/test_revision_replay.py
tests/statblocks_v1/api/test_revision_idempotency.py
```

## 12. Testing requirements

Mandatory isolated tests:

- create first revision;
- append second revision;
- read logical statblock;
- list revisions;
- exact first and second revision reads;
- first revision unchanged after append;
- create and append idempotent replay;
- idempotency conflict;
- wrong/missing parent;
- wrong statblock/revision pair;
- candidate-linked accepted edit provenance;
- validation warning accepted when ready;
- validation error blocked;
- concurrent append/idempotency behavior at application or repository level;
- no delete/update operation in OpenAPI.

Infrastructure integration test:

- create through Firestore repository;
- tear down/recreate service instance;
- exact revision read remains identical.

## 13. Acceptance criteria

PR18 is complete when:

- accepted definitions become immutable revision resources;
- exact revision replay is proven;
- revision writes are idempotent;
- append never mutates parent revision;
- read routes never silently resolve latest;
- candidate provenance is server-owned;
- DungeonBuddy receives a stable `statblock_id + revision_id` locator;
- all route tests run without production credentials through in-memory dependencies.

## 14. Non-goals

- no revision deletion or overwrite;
- no campaign preferred-revision state;
- no Threat graph write;
- no Markdown persistence;
- no legacy project migration;
- no public browser route.

## 15. Successor handoff

Before merge, update PR19 with:

- exact OpenAPI operation IDs;
- final resource/request models (no free-form provenance spoof surface);
- asset-binding model;
- revision locator format;
- pagination behavior;
- candidate acceptance/expiration policy and same-key replay after TTL;
- `created_by` = service identity; `actor` = provenance only;
- PR18 error catalog extension (idempotency/parent/stale/validation/indeterminate);
- cross-repo fixture suitable for DungeonBuddy client generation.
