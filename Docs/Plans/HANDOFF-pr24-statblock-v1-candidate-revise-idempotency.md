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
Head SHA: 0d746164e5f4bd24d6cb2622dd63b40badaad576
Current workflow run: https://github.com/Drakosfire/DungeonMindServer/actions/runs/30185843127
Failure identity (same as main/PR23):
  ERROR collecting tests/test_redteam_hardening.py
  ERROR collecting tests/test_ruleslawyer_router.py
  openai.OpenAIError: storegenerator/store_helper.py OpenAI() at import without OPENAI_API_KEY
Comparison: identical collection failure mode to predecessor PR #23 and main redteam-hardening runs.
Waiver: inherited baseline; not introduced by revise idempotency.
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
- `test_firestore_revise_replay_through_fresh_generation_service`

Paste pass counts from `revise-suite.txt` into PR review when updating this handoff.

Latest local emulator run (2026-07-25):

```text
FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
GOOGLE_CLOUD_PROJECT=demo-revise-idempotency
uv run pytest tests/statblocks_v1/integration/test_firestore_repositories.py -q --tb=short
14 passed in 2.87s
```
