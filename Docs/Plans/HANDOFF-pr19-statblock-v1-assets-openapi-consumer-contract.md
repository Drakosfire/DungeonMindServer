# HANDOFF — PR19 Statblock v1 assets, OpenAPI, and consumer contract

**Status:** IN REVIEW — rebased onto merged PR18; contract publication sealed
**Target repository:** `Drakosfire/DungeonMindServer`  
**Coordinated consumer:** `Drakosfire/DungeonMindBuddy`  
**Predecessor:** PR18 revision resource API  
**Successor:** `HANDOFF-pr20-statblock-v1-production-hardening-launch.md`

## PR18 predecessor completion notes

- Resource operation IDs are `create_statblock_v1`,
  `append_statblock_revision_v1`, `get_statblock_v1`,
  `list_statblock_revisions_v1`, and `get_statblock_revision_v1`.
- Create returns `{ statblock, revision }`; append and exact read return
  `StatblockRevisionResourceV1`; list returns `{ revisions }` chronologically.
  The durable locator is `statblock_id + revision_id`.
- Write DTOs expose typed acceptance fields only (`change_summary`,
  `accepted_through`, `actor`, `candidate_id`, `asset_bindings`). There is no
  free-form caller `provenance` object. Server-owned `provenance.candidate`
  audit evidence is attached on first write.
- `created_by` is always the service identity (`dungeonbuddy`). Caller `actor`
  is stored as provenance `accepted_by` only.
- Candidate GET returns `410` once expired. Acceptance may still reference an
  expired candidate while its server-owned record remains available. Same-key
  create/append replay survives candidate TTL deletion because idempotency is
  checked before `get_for_acceptance`.
- PR18 extends the PR17 error map with `idempotency_conflict`,
  `parent_revision_mismatch`, `stale_parent_revision`, immutable conflicts,
  `ambiguous_request_payload`, `validation_failed` (with full receipt), and
  `transaction_indeterminate`. Resource write/read OpenAPI declares the typed
  failure statuses; no PUT/PATCH/DELETE revision routes exist.
- Asset bindings are currently caller-supplied revision-envelope dictionaries;
  they are excluded from the mechanics definition digest. PR19 replaces them
  with the typed asset contract.

## 0. Mission

Make the authoritative v1 route cleanly consumable by DungeonBuddy: complete typed asset-reference behavior, deterministic OpenAPI/schema publication, generated consumer types/client, and cross-repository contract tests.

DungeonMindServer remains the sole contract owner.

## 1. Asset contract

Finalize and implement:

```text
AssetBriefV1
AssetRefV1
AssetBindingV1
```

Asset references should support at least:

```text
asset_id
provider/storage kind
canonical CDN URL
optional thumbnail/variant URLs
media type
role hints: portrait, token, full body, encounter art, alternate
prompt/generation provenance where appropriate
created_at
```

Do not embed image bytes or base64 payloads in statblock candidate/revision resources.

## 2. Asset ownership

DungeonMindServer owns:

- asset storage/generation gateway;
- durable asset ID and CDN URL contract;
- generated asset provenance;
- revision-level asset bindings supplied during acceptance.

DungeonBuddy owns:

- which image is preferred for a Threat or surface;
- crop/focal point and presentation role when campaign-specific;
- whether a candidate asset is accepted;
- Threat-level versus statblock/form-level binding.

Asset changes do not create mechanics revisions unless mechanics-relevant media is later explicitly brought into the definition contract.

## 3. Existing image pipeline adapter

Wrap current Cloudflare/image-generation behavior behind the v1 asset gateway.

Do not:

- import image upload/deletion logic into the v1 router;
- parse provider IDs from URLs in application code;
- return optimistic success when a storage operation failed;
- require image generation for a valid statblock candidate.

A candidate may succeed with an asset warning or no assets.

## 4. OpenAPI authority

Ensure v1 operation IDs, schemas, enums, discriminators, examples, and errors are stable and deterministic.

Produce a checked artifact such as:

```text
openapi/dungeonbuddy-statblocks-v1.json
```

or a deterministic extraction command whose output is validated in CI.

The artifact should include only the intended v1 contract slice or provide a reliable extraction mechanism so DungeonBuddy does not depend on unrelated server OpenAPI churn.

## 5. Generated consumer

Generate DungeonBuddy TypeScript DTOs/client from the DungeonMindServer contract.

Preferred properties:

- reproducible command;
- generated-code header with source commit/schema fingerprint;
- no hand-edited canonical DTOs;
- local DungeonBuddy projection types remain separate;
- generated output can be updated atomically when contract changes.

The exact generator may be chosen during implementation. Document version and invocation.

## 6. Cross-repository contract fixtures

Publish a small contract fixture pack containing:

- generation request;
- generated candidate response;
- edited definition validation request/response;
- create-statblock request/response;
- append-revision request/response;
- exact-revision response;
- typed error examples.

DungeonBuddy should load these fixtures through generated types and prove:

- candidate review data can be parsed;
- exact revision locator is retained;
- combat-seed projection can derive minimum operational fields;
- no Markdown is required;
- unknown contract drift fails loudly.

## 7. Drift detection

Add CI behavior that detects:

- OpenAPI/schema changed without regenerated artifact;
- generated DungeonBuddy types stale relative to authoritative fingerprint;
- fixture no longer validates;
- discriminator or enum change not reflected in consumer.

Avoid requiring a live DungeonBuddy checkout in every DungeonMindServer unit test if that makes CI fragile. A coordinated consumer PR or versioned artifact check is acceptable.

## 8. Contract versioning

Lock policy for v1 changes:

- additive compatible changes and whether they require minor version bump;
- breaking changes require new contract version/route namespace or explicit pre-launch reset policy;
- schema fingerprint is not a substitute for semantic version;
- once DungeonBuddy production integration launches, contract changes require consumer verification.

Because the route is pre-launch, implementation may still refine `1.0.0` before PR20, but all such changes must update artifacts and fixtures.

## 9. Suggested files

```text
statblocks_v1/domain/assets.py
statblocks_v1/application/assets.py
statblocks_v1/infrastructure/asset_gateway.py
statblocks_v1/infrastructure/cloudflare_asset_gateway.py
openapi/dungeonbuddy-statblocks-v1.json
scripts/export_dungeonbuddy_statblock_openapi.py
Docs/Design/fixtures/dungeonbuddy-statblock-v1-api/*.json
tests/statblocks_v1/test_asset_contract.py
tests/statblocks_v1/test_openapi_artifact.py
```

Coordinated DungeonBuddy files are determined in its PR, but the generated output must identify DungeonMindServer as source.

## 10. Testing requirements

DungeonMindServer:

- asset reference round-trip;
- asset gateway fake and failure behavior;
- mechanics digest unchanged by envelope asset binding changes;
- deterministic OpenAPI export;
- every fixture validates against authoritative models;
- expected operation IDs and discriminators are present;
- drift test fails on stale artifact.

DungeonBuddy coordinated smoke:

- generated client/types compile;
- fixtures parse;
- candidate can be projected;
- exact revision can seed combat minimums;
- `human_adjudicated` mechanics remain renderable and non-automated.

## 11. Acceptance criteria

PR19 is complete when:

- DungeonMindServer publishes one deterministic v1 contract artifact;
- DungeonBuddy consumes generated rather than handwritten canonical types;
- asset references are typed and CDN-backed;
- asset failure cannot invalidate otherwise valid mechanics without explicit policy;
- cross-repo fixtures cover the full authoring/acceptance/replay loop;
- contract drift is detected automatically;
- no display or campaign image preference leaks into mechanics digest.

## 12. Non-goals

- no DungeonBuddy final UI design;
- no image editor;
- no Threat graph write;
- no legacy image migration;
- no public asset deletion API;
- no production rollout yet.

## 13. Successor handoff

Before merge, update PR20 with:

- authoritative OpenAPI artifact path/fingerprint;
- generated client command and output path;
- final route operation IDs;
- required asset environment settings;
- cross-repo smoke command;
- any pre-launch contract changes still pending.
