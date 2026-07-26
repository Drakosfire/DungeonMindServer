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
Reviewed failing head: 6fc5f692d57fc7269702f8ed35073e4ebd0fe602
Workflow run (that head): https://github.com/Drakosfire/DungeonMindServer/actions/runs/30185843127
Job: https://github.com/Drakosfire/DungeonMindServer/actions/runs/30185843127/job/89750285125
Failure identity (collected from that job log):
  ERROR collecting tests/test_redteam_hardening.py
  ERROR collecting tests/test_ruleslawyer_router.py
  openai.OpenAIError: The api_key client option must be set ...
  Root cause: storegenerator/store_helper.py:5 client = OpenAI() at import time
Comparison: identical collection failure on main and predecessor PR #23 redteam-hardening runs.
Waiver: inherited baseline; not introduced by revise idempotency. Subsequent heads that
only change revise-ops/fixtures inherit this waiver while the failure identity is unchanged.
```

## Emulator evidence (Firestore revise durability)

Run against a live Firestore emulator (do not commit emulator data):

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
export GOOGLE_CLOUD_PROJECT=demo-revise-idempotency
uv run pytest tests/statblocks_v1/integration/test_firestore_repositories.py -q --tb=short \
  | tee /tmp/firestore-emulator/revise-suite.txt
```

Revise-focused tests in that module:

- `test_firestore_revise_ops_atomic_complete_and_replay`
- `test_firestore_revise_ops_concurrent_first_claims_reserve_one_candidate_id`
- `test_firestore_revise_ops_expired_lease_takeover_retains_reserved_candidate_id`
- `test_firestore_revise_ops_indeterminate_complete_reconciles`
  (stale-worker complete convergence + post-commit transaction() boom → reconcile)
- `test_firestore_revise_replay_through_fresh_generation_service`

Latest executed emulator run (2026-07-25, recorded in review response):

```text
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
GOOGLE_CLOUD_PROJECT=demo-revise-idempotency
uv run pytest tests/statblocks_v1/integration/test_firestore_repositories.py \
  tests/statblocks_v1/test_api_fixtures.py -q --tb=short
17 passed
```
