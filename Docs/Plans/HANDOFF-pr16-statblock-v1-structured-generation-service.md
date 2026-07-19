# HANDOFF — PR16 Statblock v1 Structured Outputs generation service

**Status:** READY AFTER PR14; INTEGRATES PR15  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessors:** PR13 contract, PR14 trust core, PR15 repository protocols  
**Successor:** `HANDOFF-pr17-statblock-v1-candidate-api.md`

## PR15 predecessor completion notes

- Use synchronous `CandidateRepository.create/get` and `StatblockPersistenceRepository`
  (`create_statblock`, `append_revision`, `get`, `get_revision`); async callers must
  offload calls with `asyncio.to_thread`.
- Offline fixtures can use `InMemoryCandidateRepository` and
  `InMemoryStatblockPersistenceRepository(clock=..., id_factory=DeterministicIdFactory())`.
- Candidate IDs use `cand_<base36>`; statblock/revision IDs use `sb_<base36>` and
  `rev_<base36>`. Candidate TTL is enforced by `expires_at`; Firestore TTL must also
  be configured on that field.
- `compute_request_digest(operation, payload)` covers complete operation parameters
  with the definition component as PR14 canonical JSON plus NFC-normalized remaining
  strings; it is distinct from the definition digest.
  Create/append idempotency outcomes pin `IdempotencyOutcomeV1(statblock_id, revision_id)`
  so create replay returns the original revision after later appends.
  Append is compare-and-swap against `latest_revision_id` (`stale_parent_revision`).
  Firestore collections are `dungeonbuddy_statblock_candidates_v1`,
  `dungeonbuddy_statblocks_v1` with `revisions` subcollections, and
  `dungeonbuddy_statblock_idempotency_v1`. Candidate `expires_at` is a native timestamp.

## 0. Mission

Implement the provider-independent application service that generates and revises `StatblockDefinitionV1` using OpenAI Structured Outputs, validates the result, persists a server-owned candidate record, and returns `GeneratedStatblockCandidateV1`.

Do not add HTTP endpoints in this PR.

## 1. Core boundary

The model generates only:

```text
StatblockDefinitionV1
```

DungeonMindServer creates:

```text
candidate_id
contract/version
generation receipt
validation receipt
asset brief/assets
created/expires timestamps
```

The provider never generates server IDs, digests, timestamps, or lifecycle state.

## 2. Required application models

Implement generation and revision commands consistent with the authoritative design.

Generation request concerns:

```text
request_id
ruleset
source name/description snapshot and digest
intent: CR, roles, complexity, must include/avoid
encounter/terrain context
asset options
caller provenance
```

Revision request concerns:

```text
request_id
source definition or exact revision locator
revision instructions
preserve-element-key policy
context/intent changes
asset options
caller provenance
```

## 3. Provider protocol

Define a narrow provider protocol such as:

```text
generate_definition(prompt, response_model/schema, provider_options)
```

Provide:

- deterministic fake provider for tests;
- OpenAI provider adapter;
- typed provider outcomes for success, refusal, incomplete output, timeout, rate limit, and provider failure.

Do not return raw provider exceptions to application callers.

## 4. Structured schema compiler

Compile the OpenAI strict-compatible schema from the canonical Pydantic models.

Requirements:

- semantic equivalence with canonical contract;
- no handwritten parallel schema;
- deterministic output and schema fingerprint;
- compatibility tests for discriminated mechanic/effect unions;
- explicit handling of optional fields and `additionalProperties`;
- no silent removal of contract fields;
- schema/compiler version recorded in generation receipt.

Reuse lessons from the current `_make_schema_strict` code, not that implementation blindly.

## 5. Prompt builder

Create a versioned prompt builder driven by request intent and the new schema.

It must:

- distinguish D&D 5e 2014 and 2024 rulesets;
- explain definition-local semantic keys;
- explain section versus activation versus mechanic kind;
- require complete table-facing `rules_text` alongside typed semantics;
- direct uncertain mechanics into `human_adjudicated` rather than invented fields;
- avoid requesting server metadata;
- avoid long irrelevant examples that bias every creature;
- include source description and explicit must/must-not constraints;
- preserve source element keys during revision when conceptually retained.

Prompt version is a first-class receipt field.

## 6. Generation service flow

```text
validate request
→ build prompt
→ compile/select schema
→ call provider
→ parse StatblockDefinitionV1
→ run candidate-mode semantic validation
→ canonicalize and digest
→ build generation + validation receipts
→ create candidate record with expiration
→ return GeneratedStatblockCandidateV1
```

A warning-bearing candidate may be returned for human review. A structurally invalid or reference-incoherent definition must not become a candidate.

## 7. Revision flow

Support revision from:

- submitted complete definition; or
- exact persisted revision resolved by repository.

The revision result is a new candidate, not a new accepted revision.

Validate that retained conceptual rule elements preserve stable local keys where reasonable. Key changes may warn rather than fail when the element is genuinely replaced.

## 8. Receipts

Generation receipt should include at least:

```text
request_id
provider
model
prompt_version
schema/compiler version and fingerprint
generated_at
source description digest
source candidate/revision locator if applicable
provider request/response identifiers when safe
latency/tokens if available
```

Do not store API keys or full hidden provider payloads.

## 9. Asset brief

The generation service may derive a typed `AssetBriefV1` from the request and definition.

Actual image generation is optional and should occur only when requested. Asset generation failures should not destroy a valid statblock candidate; return typed partial outcome/warnings.

## 10. Configuration

Provider model, timeout, and retry policy must be settings, not hard-coded in the service.

The current hard-coded historical model string is not carried forward as contract behavior.

## 11. Suggested files

```text
statblocks_v1/application/commands.py
statblocks_v1/application/generation.py
statblocks_v1/application/prompts.py
statblocks_v1/application/schema_compiler.py
statblocks_v1/infrastructure/openai_provider.py
statblocks_v1/infrastructure/fake_provider.py
tests/statblocks_v1/test_generation_service.py
tests/statblocks_v1/test_prompt_builder.py
tests/statblocks_v1/test_schema_compiler.py
tests/statblocks_v1/integration/test_openai_generation.py
```

## 12. Testing requirements

Mandatory offline tests:

- fake provider returns simple and advanced valid fixtures;
- generated candidate is persisted and retrievable;
- candidate receipt contains deterministic request/source information;
- refusal, incomplete, timeout, and malformed output map to typed outcomes;
- semantic validation warnings survive candidate creation;
- structural/reference invalid output is rejected;
- revision preserves or intentionally replaces local keys;
- asset failure does not erase a valid candidate;
- no test requires network credentials.

Opt-in live tests:

- one simple generation;
- one mythic/advanced generation;
- response validates against canonical model;
- no outer server metadata appears in model output.

## 13. Acceptance criteria

PR16 is complete when:

- one application service generates canonical v1 definitions through a fake and OpenAI adapter;
- model output uses the same domain type later persisted;
- candidate provenance is server-owned and stored;
- provider failure cases are typed;
- ordinary tests are fully offline;
- no FastAPI route is added.

## 14. Non-goals

- no candidate HTTP endpoints;
- no accepted revision creation;
- no DungeonBuddy client;
- no legacy generator adapter requirement;
- no canonical Markdown.

## 15. Successor handoff

Before merge, update PR17 with:

- command and service signatures;
- dependency factory/override pattern;
- typed generation outcome catalog;
- candidate repository behavior;
- settings names;
- test fixtures and fake-provider helpers.
