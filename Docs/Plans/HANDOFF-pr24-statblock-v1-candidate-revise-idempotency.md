# HANDOFF — PR24 statblock v1 candidate revise idempotency

## Capability

`POST /api/internal/dungeonbuddy/v1/statblock-candidates:revise` is durable on
`(caller_scope, request_id)` with a canonical body digest, parallel to PR23
generate idempotency.

- Same `request_id` + same digest → same `candidate_id`, no second provider call.
- Same `request_id` + different digest → `409 idempotency_conflict`.
- Lost-response recovery via POST replay (no GET-by-request_id route).

## Persistence

Collection: `dungeonbuddy_statblock_candidate_revise_ops_v1`  
Doc id: `sha256(caller_scope || 0x1f || "revise_candidate" || 0x1f || request_id)`

## Digest (excludes `request_id`)

`ruleset`, `revision_instructions`, XOR `source_definition` / `source_locator`,
optional `source`, `intent`, `context`, `asset_options`, `preserve_element_keys`,
`actor`.

Outcome binding uses operation string `revise_candidate_outcome`.
