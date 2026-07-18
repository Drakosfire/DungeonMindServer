# Statblock v1 Firestore layout

Canonical v1 persistence is isolated from legacy statblock collections:

```text
dungeonbuddy_statblock_candidates_v1/{cand_<base36>}
dungeonbuddy_statblocks_v1/{sb_<base36>}
  revisions/{rev_<base36>}
dungeonbuddy_statblock_idempotency_v1/{sha256(scope, operation, key)}
```

Candidate documents contain `expires_at`. Configure a Firestore TTL policy on
`dungeonbuddy_statblock_candidates_v1.expires_at`; TTL cleanup is asynchronous,
so reads enforce expiration independently. Revisions have no TTL and are never
updated or deleted by this adapter.

The only expected query is revisions beneath a known statblock. If chronological
listing is required, add a composite/index configuration for `created_at`
according to the deployed Firestore project; the current adapter streams the
subcollection and does not require one.

Firestore's Python client is synchronous. Repository methods intentionally
remain synchronous; async application/API callers must invoke each operation
through `asyncio.to_thread`, never directly on the event-loop thread.
