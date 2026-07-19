# HANDOFF — PR17 Statblock v1 candidate API

**Status:** READY AFTER PR15 AND PR16  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessors:** repository persistence and generation service  
**Successor:** `HANDOFF-pr18-statblock-v1-revision-resource-api.md`

## PR15 predecessor completion notes

- Use the synchronous repository protocols from `statblocks_v1.application.repositories`;
  route/service code must use `await asyncio.to_thread(...)` for Firestore calls.
- `InMemoryCandidateRepository` and `InMemoryStatblockPersistenceRepository` accept
  deterministic clock and ID fixtures. IDs are `cand_<base36>`, `sb_<base36>`, and
  `rev_<base36>`.
- Candidates expire at `expires_at` (also the Firestore TTL field). Collections are
  `dungeonbuddy_statblock_candidates_v1`, `dungeonbuddy_statblocks_v1/revisions`,
  and `dungeonbuddy_statblock_idempotency_v1`.
- Reuse `compute_request_digest(operation, payload)` for request replay: it includes
  operation parameters rather than using only the mechanics definition digest.

## PR16 predecessor completion notes

- Application entry points are `GenerationServiceV1.generate(GenerateStatblockCommandV1)`
  and `GenerationServiceV1.revise(ReviseStatblockCommandV1)`. Both return either
  `GeneratedStatblockCandidateV1` or `GenerationFailureV1`; routes must map the latter
  without exposing provider exceptions (provider exceptions are caught at the service
  boundary as `provider_failure`).
- Construct the service through dependency injection with a `DefinitionProvider`,
  `CandidateRepository`, `GenerationSettingsV1`, clock, candidate-ID factory, and,
  for revision locators, `PersistenceDefinitionResolver` over
  `StatblockPersistenceRepository.get_revision(statblock_id, revision_id)`.
  Revision commands use `ExactRevisionLocatorV1(statblock_id, revision_id)`, not a
  single-id `ResourceLocatorV1`. Tests use `FakeDefinitionProvider` plus
  `InMemoryCandidateRepository`.
- Provider outcomes are `success`, `refusal`, `incomplete`, `timeout`, `rate_limit`,
  and `failure`; application failures are prefixed `provider_`, with
  `definition_invalid`, `ruleset_mismatch`, `source_digest_mismatch`, and
  resolver codes (`revision_not_found`, `statblock_not_found`, `source_unavailable`)
  reserved for service-level failures.
- Generation receipts store server-owned `caller_scope`/`actor` provenance, a
  server-computed (optionally caller-verified) source description digest, and for
  every revision a PR14 `source_definition_digest` of the exact mechanics revised
  (inline submitted definition or resolved locator revision). Description digests
  never substitute for mechanics provenance.
  Warning-bearing candidate receipts may be persisted; invalid receipts are not.
  `preserve_element_keys` is a versioned post-validation pass
  (`validator_version` gains `+statblock-key-preservation-v1`) emitting
  `ELEMENT_KEY_CHANGED`, `ELEMENT_KEY_DROPPED`, `ELEMENT_KEY_REPURPOSED`, and
  `ELEMENT_KEY_IDENTITY_AMBIGUOUS`.
  Asset partial outcomes use typed `AssetWarningV1` codes
  (`asset_generator_unconfigured`, `asset_generation_failed`). When
  `generate_images=True`, the exact effective `AssetBriefV1` passed to the
  generator is always persisted on the candidate (name fallback when
  `include_generation_brief=False`).
- Settings are `STATBLOCKS_V1_OPENAI_MODEL`,
  `STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS`, `STATBLOCKS_V1_OPENAI_MAX_RETRIES`, and
  `STATBLOCKS_V1_CANDIDATE_TTL_SECONDS`. Values are validated on the settings
  model itself (non-empty model, finite timeout `> 0`, retries `>= 0`, TTL `> 0`);
  malformed env input raises `InternalServiceMisconfiguredError`. The default
  model resolves the in-repo `DungeonMindServer/MODEL_POLICY.json` action
  `structured_generation`; missing policy raises
  `InternalServiceMisconfiguredError` unless the env override is set.
- `FakeDefinitionProvider` accepts a JSON payload or `ProviderOutcomeV1` and records
  calls. It supports offline route tests; `candidate_id_factory` and clock make
  receipts/candidate expiry deterministic.

## 0. Mission

Expose the generation, revision, validation, and candidate-read operations through the dedicated authenticated DungeonBuddy v1 router.

This PR makes candidate workflows usable but does not yet allow accepted immutable revision creation.

## 1. Routes

Implement:

```text
POST /api/internal/dungeonbuddy/v1/statblock-candidates:generate
POST /api/internal/dungeonbuddy/v1/statblock-candidates:revise
POST /api/internal/dungeonbuddy/v1/statblock-definitions:validate
GET  /api/internal/dungeonbuddy/v1/statblock-candidates/{candidate_id}
```

Update health/capability discovery to advertise only implemented operations.

## 2. HTTP boundary

The router should:

```text
parse request DTO
→ resolve authenticated caller context
→ invoke application service
→ map typed outcome to typed response/HTTP status
```

It must not:

- build prompts;
- call OpenAI directly;
- access Firestore directly;
- canonicalize or validate independently;
- render Markdown;
- calculate copied combat defaults;
- import the legacy statblock router.

## 3. Request and response models

Use the canonical contract models from the v1 package. API wrappers may add request IDs, caller context, and typed error envelopes, but must not duplicate the mechanics schema.

Candidate response must include:

```text
candidate_id
contract/version
definition
validation receipt
generation receipt
asset brief/assets
created/expires timestamps
```

## 4. Validation endpoint

The validation endpoint accepts a complete `StatblockDefinitionV1` and returns a validation receipt plus canonical digest.

It does not persist a candidate or revision unless the contract explicitly defines an optional preview record. Default behavior is pure validation.

DungeonBuddy mechanical edits use this route before acceptance and may also receive validation as part of revision creation later.

## 5. Candidate read

Candidate reads are exact by `candidate_id`.

Return typed outcomes for:

- found;
- not found;
- expired;
- caller not authorized if candidate ownership/scope applies.

Do not silently regenerate an expired candidate.

## 6. Authentication and caller provenance

Apply service authentication at router level.

Create a caller context available to application services, including a stable service identity such as `dungeonbuddy` and request correlation ID.

Initial shared-key authentication is acceptable. Do not expose whether a key is absent from server configuration versus invalid to an unauthenticated caller beyond safe operational semantics.

## 7. Error envelope

Use one v1 error envelope with stable codes and field/reference details where safe.

Required mappings include:

```text
invalid_request → 422
validation_failed → 422
candidate_not_found → 404
candidate_expired → 410
provider_refused/incomplete → suitable typed 4xx/5xx policy
provider_timeout/unavailable → 503/504 policy
rate_limited → 429
internal_misconfiguration → 503
unauthenticated → 401
forbidden → 403
```

Do not return raw exception strings or provider payloads.

## 8. Dependency injection

Use the PR12 dependency seam to inject:

- generation/revision service;
- validator;
- candidate repository;
- clock/caller context where relevant.

Route tests must replace all external dependencies with fake or in-memory implementations.

## 9. Idempotency and retries

Generation and revision requests should accept stable request IDs. Decide and document whether they are idempotent operations.

Recommended:

- same caller + request ID + same request returns the same candidate;
- same request ID with different request body returns conflict;
- provider invocation is not repeated after a successful stored result.

Use the PR15 idempotency service if implemented for candidate commands; do not invent a separate route-local cache.

## 10. Suggested files

```text
statblocks_v1/api/models.py
statblocks_v1/api/router.py
statblocks_v1/api/error_mapping.py
statblocks_v1/api/dependencies.py
tests/statblocks_v1/api/test_candidate_routes.py
tests/statblocks_v1/api/test_validation_route.py
tests/statblocks_v1/api/test_candidate_auth.py
```

## 11. Testing requirements

Use an isolated FastAPI app.

Required route tests:

- health capabilities;
- generate success with fake provider;
- revise success from definition and exact revision source;
- validate success/warnings/failure;
- candidate exact read;
- candidate expired/not found;
- missing/wrong/correct authentication;
- request ID replay;
- conflicting request ID reuse;
- provider refusal, timeout, and malformed output mapping;
- no Markdown or `combat_defaults` in response;
- OpenAPI paths and response models exist.

No route test may require OpenAI or Firestore credentials.

## 12. Acceptance criteria

PR17 is complete when:

- DungeonBuddy can request and retrieve a typed candidate through the v1 router;
- validation accepts complete edited definitions;
- candidate provenance is persisted server-side;
- all failures use stable typed envelopes;
- route tests run offline against dependency overrides;
- the health endpoint advertises accurate capabilities;
- no acceptance/revision resource route exists yet.

## 13. Non-goals

- no logical statblock creation;
- no immutable revision append;
- no DungeonBuddy UI work;
- no generated client publication;
- no legacy endpoint changes;
- no image-selection workflow.

## 14. Successor handoff

Before merge, update PR18 with:

- final route prefix and auth dependency;
- API error envelope and status policy;
- request ID/idempotency behavior;
- candidate lookup/service signatures;
- OpenAPI path names;
- route-test app factory and dependency overrides.
