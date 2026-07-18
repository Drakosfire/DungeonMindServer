# HANDOFF — PR15 Statblock v1 repositories and immutable persistence

**Status:** READY AFTER PR14  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessor:** PR14 trust core  
**Successor:** `HANDOFF-pr16-statblock-v1-structured-generation-service.md`

## 0. Mission

Implement repository protocols, deterministic in-memory repositories, and Firestore adapters for generated candidates, logical statblocks, immutable revisions, and idempotency outcomes.

This PR establishes durable truth but does not expose the final HTTP resource routes.

## 1. Required resources

### Candidate record

```text
candidate_id
contract/version
definition
validation receipt
generation receipt
asset brief/assets
created_at
expires_at
source candidate/revision locator when revised
```

Candidates may expire. Accepted revisions do not.

### Logical statblock

```text
statblock_id
latest_revision_id
created_at
created_by
```

`latest_revision_id` is chronological server metadata, not a DungeonBuddy campaign preference.

### Immutable revision

```text
statblock_id
revision_id
parent_revision_id
contract/version
canonical definition
definition digest
validation receipt
provenance
asset bindings
created_at
```

### Idempotency record

```text
caller scope
operation
idempotency key
request digest
outcome resource locator
created_at
```

## 2. Repository protocols

Define narrow application-facing protocols, for example:

```text
CandidateRepository
StatblockRepository
RevisionRepository
IdempotencyRepository
```

Do not expose Firestore document APIs above the infrastructure layer.

Provide in-memory implementations with deterministic behavior for application and route tests.

## 3. Firestore layout

Choose and document one explicit layout. A likely shape:

```text
dungeonbuddy_statblock_candidates_v1/{candidate_id}

dungeonbuddy_statblocks_v1/{statblock_id}
  revisions/{revision_id}

dungeonbuddy_statblock_idempotency_v1/{scoped_key}
```

Alternative layouts are allowed when transaction behavior and query needs are better served, but do not reuse:

```text
statblock_projects
statblock_sessions
statblock_creatures
```

as canonical v1 storage.

## 4. Transaction and append behavior

### Create logical statblock

Atomically:

1. verify idempotency key;
2. validate persistence-ready receipt/digest inputs;
3. allocate `statblock_id` and first `revision_id`;
4. write logical statblock metadata;
5. write first immutable revision;
6. write idempotency outcome.

### Append revision

Atomically:

1. verify idempotency key;
2. load logical statblock;
3. verify parent revision exists and belongs to statblock;
4. write new immutable revision;
5. update chronological `latest_revision_id`;
6. write idempotency outcome.

Do not overwrite a revision document even when the caller supplies the same ID. IDs are server-owned.

## 5. Idempotency semantics

Required behavior:

```text
same key + same request digest
  → return original successful outcome

same key + different request digest
  → typed idempotency conflict

retry after partial infrastructure error
  → reconcile transaction outcome before creating anything new
```

The request digest is not the definition digest alone; it should distinguish create/append operation parameters and parent/candidate intent.

## 6. Candidate persistence

Generated candidates should be persisted by DungeonMindServer so later acceptance can trust server-owned provenance.

Candidate records need TTL/expiration semantics. The PR may document required Firestore TTL configuration if infrastructure configuration cannot be committed here.

Acceptance should still submit the complete definition because the GM may edit it. A candidate locator links provenance; it does not replace the submitted accepted definition.

## 7. Blocking I/O

The current Firestore client is synchronous. Do not call it directly from async route handlers in later PRs.

This PR should make one policy explicit:

- repository methods are synchronous and invoked through a thread boundary by application/API code; or
- infrastructure adapter methods are async wrappers that offload blocking work.

Choose one and test it. Do not create async-looking methods that block the event loop invisibly.

## 8. Failure model

Define typed domain/application errors for at least:

- candidate not found/expired;
- statblock not found;
- revision not found;
- parent revision mismatch;
- immutable revision conflict;
- idempotency conflict;
- persistence unavailable;
- transaction indeterminate/reconciliation required.

Infrastructure exceptions must not leak as raw HTTP details later.

## 9. Suggested files

```text
statblocks_v1/domain/resources.py
statblocks_v1/application/repositories.py
statblocks_v1/infrastructure/memory_repositories.py
statblocks_v1/infrastructure/firestore_repositories.py
statblocks_v1/infrastructure/firestore_layout.md
tests/statblocks_v1/test_memory_repositories.py
tests/statblocks_v1/test_revision_service.py
tests/statblocks_v1/integration/test_firestore_repositories.py
```

## 10. Testing requirements

### In-memory tests — mandatory

- create first revision;
- append child revision;
- exact revision replay;
- latest revision metadata advances;
- old revision remains unchanged;
- idempotent create retry;
- idempotent append retry;
- conflicting idempotency reuse;
- missing/wrong parent;
- same definition may appear in different revisions if intentionally submitted;
- candidate expiration.

### Firestore tests — mandatory but may be emulator-gated

- collection layout;
- transaction atomicity;
- concurrent append behavior;
- exact JSON round-trip;
- TTL field presence;
- indexes/config requirements documented.

Ordinary CI must still run the in-memory suite without credentials.

## 11. Acceptance criteria

PR15 is complete when:

- repository interfaces contain no FastAPI concerns;
- in-memory repositories support all successor tests;
- Firestore storage is separate from legacy project documents;
- accepted revisions are demonstrably append-only;
- exact replay returns canonical definition and digest;
- idempotency behavior is deterministic and tested;
- blocking I/O policy is explicit;
- no final public/internal HTTP resource route is added yet.

## 12. Non-goals

- no OpenAI generation;
- no candidate HTTP route;
- no DungeonBuddy client generation;
- no legacy data migration;
- no deletion of old statblocks;
- no latest-to-preferred campaign semantics.

## 13. Successor handoff

Before merge, update PR16 and PR17 with:

- repository protocol signatures;
- in-memory fixture constructors;
- Firestore collection names;
- candidate expiration policy;
- ID formats;
- idempotency request-digest function;
- exact thread/offload policy for Firestore operations.
