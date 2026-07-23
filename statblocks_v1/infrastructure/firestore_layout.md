# Statblock v1 Firestore layout

Canonical v1 persistence is isolated from legacy statblock collections:

```text
dungeonbuddy_statblock_candidates_v1/{cand_<base36>}
dungeonbuddy_statblocks_v1/{sb_<base36>}
  revisions/{rev_<base36>}
dungeonbuddy_statblock_idempotency_v1/{sha256(scope, operation, key)}
dungeonbuddy_statblock_candidate_generate_ops_v1/{sha256(scope, generate_candidate, request_id)}
```

Candidate documents contain `expires_at` stored as a native Firestore timestamp
(not a JSON string). Configure a Firestore TTL policy on
`dungeonbuddy_statblock_candidates_v1.expires_at`; TTL cleanup is asynchronous,
so reads enforce expiration independently. Revisions have no TTL and are never
updated or deleted by this adapter.

Candidate generate-operation documents (PR23) outlive candidate TTL. Do **not**
configure TTL on `dungeonbuddy_statblock_candidate_generate_ops_v1`. Document IDs
are `sha256(caller_scope || 0x1f || "generate_candidate" || 0x1f || request_id)`.
Stored `caller_scope`, `operation`, and `request_id` must match those key
components; mismatches fail closed as integrity errors. Records reserve one
`candidate_id` before provider work and transition `pending → completed|failed`.
On completion they **must** retain `candidate_expires_at` (without embedding
mechanics) equal to the persisted candidate's `expires_at` so premature candidate
loss fails closed as an integrity error while post-expiry TTL deletion returns
typed expiry. A completed record missing `candidate_expires_at` is malformed and
must not be treated as ordinary expiry. Replay treats `operation.candidate_expires_at`
as the authority for 410 decisions, but a present candidate whose `expires_at`
disagrees with that field is an integrity failure (not success and not 410).
Completed operations also retain `outcome_digest` (canonical fingerprint of the
full persisted candidate payload) so replay cannot accept a recreated candidate
that only copies a subset of fields. Candidate create and operation completion
share one Firestore transaction. Pending operations must not coexist with a
candidate document; that impossible state fails closed as integrity rather than
being promoted to completed. Completed replay verifies the candidate generation
receipt binds `request_id`, `caller_scope`, and `request_digest`, and that the
computed outcome fingerprint matches `outcome_digest`.

The only expected query is revisions beneath a known statblock. If chronological
listing is required, add a composite/index configuration for `created_at`
according to the deployed Firestore project; the current adapter streams the
subcollection and does not require one.

Firestore's Python client is synchronous. Repository methods intentionally
remain synchronous; async application/API callers must invoke each operation
through `asyncio.to_thread`, never directly on the event-loop thread.
