# HANDOFF — PR24 statblock v1 candidate revise idempotency

## Capability

`POST /api/internal/dungeonbuddy/v1/statblock-candidates:revise` is durable on
`(caller_scope, request_id)` with a canonical body digest, parallel to PR23
generate idempotency.

- Same `request_id` + same digest → same `candidate_id`, no second provider call.
- Same `request_id` + different digest → `409 idempotency_conflict`.
- Lost-response recovery via POST replay (no GET-by-request_id route).

## Locator ordering (non-negotiable)

`GenerationServiceV1.revise` calls `begin_revise` **before** `source_locator` /
`source_definition` resolution (`_materialize_revise_intent` runs only after
`ReviseBeginClaimed`). Completed replay and digest conflict therefore win over
transient persistence or revision-not-found errors on replay paths.

## Persistence

Collection: `dungeonbuddy_statblock_candidate_revise_ops_v1`  
Doc id: `sha256(caller_scope || 0x1f || "revise_candidate" || 0x1f || request_id)`

## Digest (excludes `request_id`)

`ruleset`, `revision_instructions`, XOR `source_definition` / `source_locator`,
optional `source`, `intent`, `context`, `asset_options`, `preserve_element_keys`,
`actor`.

Outcome binding uses operation string `revise_candidate_outcome`.

## CI baseline waiver

```text
Workflow: redteam-hardening.yml
Run (this PR): https://github.com/Drakosfire/DungeonMindServer/actions/runs/30176374090
Failure identity:
  ERROR collecting tests/test_redteam_hardening.py
  ERROR collecting tests/test_ruleslawyer_router.py
  Root cause: storegenerator/store_helper.py:5 client = OpenAI() at import time without OPENAI_API_KEY
Predecessor PR #23 / main: same workflow fails with the same collection errors (not introduced by revise idempotency).
Waiver: out of scope for this PR; not a revise-ops regression.
```
