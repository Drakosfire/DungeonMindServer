# HANDOFF — PR23 Candidate generation request idempotency

**Created:** 2026-07-22
**Status:** ACTIVE — dispatch exactly one implementation capability.
**Target repository:** `Drakosfire/DungeonMindServer`
**Canonical handoff path:** `Docs/Plans/HANDOFF-pr23-statblock-v1-candidate-generate-idempotency.md`
**Implementation base:** `5d17e7521d086914dc67bec1f05a0c0b69547797`
**Suggested branch:** `feat/statblocks-v1-candidate-generate-idempotency`

---

## §0 Capability decomposition decision

| Candidate outcome                                 | Independently useful? | Durable contract changed? | Failure model changed? | Decision                                             |
| ------------------------------------------------- | --------------------: | ------------------------: | ---------------------: | ---------------------------------------------------- |
| Idempotent `statblock-candidates:generate` replay |                   Yes |                       Yes |                    Yes | Include                                              |
| Candidate lookup by `request_id`                  |                   Yes |                       Yes |                    Yes | Successor; not required if POST replay is sufficient |
| Candidate revision idempotency                    |                   Yes |                       Yes |                    Yes | Successor                                            |
| Generic async-operation/status API                |                   Yes |                       Yes |                    Yes | Out of scope                                         |
| DungeonMindBuddy reconciliation changes           |                   Yes |                       Yes |                    Yes | Separate repository/successor                        |
| Candidate cleanup or administrative controls      |                   Yes |                       Yes |                    Yes | Successor                                            |

**Selected capability:** durable request-key idempotency for candidate generation.

**Why this is one capability:** every changed layer establishes or proves one invariant: one authenticated caller, one generation request ID, and one request digest resolve to at most one persisted candidate and one replayable outcome.

**Named successors:**

* candidate revision idempotency;
* request-ID lookup or general operation-status routes;
* operation cancellation;
* administrative recovery tooling;
* DungeonMindBuddy adoption and removal of its temporary terminal-abandon behavior.

---

## §1 Mission

DungeonBuddy can safely retry an uncertain candidate-generation request and receive the original persisted candidate without generating a second candidate.

**Invariant**

```text
For one caller_scope + operation + request_id:

- the first accepted request reserves one stable candidate_id;
- the same request digest resolves to that same candidate and outcome;
- a different request digest returns an explicit idempotency conflict;
- no replay creates a second persisted candidate;
- the provider is never called by an ordinary completed replay.
```

**Mission falsification test**

```text
This is not one slice if implementation must also deliver revision idempotency,
a generic background-job API, request cancellation, operator tooling, or
DungeonMindBuddy changes.
```

---

## §2 Context, authority, and boundaries

### Parent authority

DungeonMindBuddy PR #388 is blocked because an HTTP timeout may occur after DungeonMindServer has persisted a candidate but before Buddy receives its `candidate_id`.

Buddy currently cannot resolve that ambiguity safely:

* retrying may generate another candidate;
* refusing to retry may permanently orphan the successful candidate.

The accepted SBW03 contract requires:

```text
same draft version + same idempotency key
→ same downstream operation/result or explicit replay conflict
```

It also contains this stop condition:

```text
Stop if downstream success can be lost without any durable candidate locator.
```

### Current Server behavior

Merged DungeonMindServer PR #17 deliberately deferred candidate idempotency:

```text
- request_id is correlation metadata only;
- identical request_id values may produce distinct candidates;
- there is no candidate-level replay;
- there is no conflict check;
- there is no provider-once or candidate reservation.
```

The current API supports:

```text
POST /api/internal/dungeonbuddy/v1/statblock-candidates:generate
GET  /api/internal/dungeonbuddy/v1/statblock-candidates/{candidate_id}
```

Candidate reads require a known `candidate_id`; there is no lookup by `request_id`.

The current generation service calls the provider, constructs a newly allocated candidate, and then writes that candidate through `CandidateRepository.create`.

### Authority precedence

```text
1. Current DungeonMindServer repository code and tests at the immutable base
2. Merged PR17 candidate API contract
3. PR15 persistence and idempotency contracts
4. This checked-in handoff
5. DungeonMindBuddy SBW03 handoff and PR #388 blocker report
6. Chat summaries
```

### Predecessor contracts

Read these before implementation:

1. `Docs/Plans/HANDOFF-pr17-statblock-v1-candidate-api.md`
2. `Docs/Plans/HANDOFF-pr15-statblock-v1-repositories-persistence.md`
3. `Docs/Plans/HANDOFF-pr16-statblock-v1-structured-generation-service.md`
4. `statblocks_v1/api/router.py`
5. `statblocks_v1/application/generation.py`
6. `statblocks_v1/application/repositories.py`
7. `statblocks_v1/infrastructure/firestore_repositories.py`
8. current candidate route, generation-service, memory-repository, and Firestore integration tests

### Important predecessor constraint

Do not silently widen the existing PR15 `IdempotencyRecordV1`.

Its outcome is specifically shaped for immutable statblock and revision creation:

```text
statblock_id
revision_id
```

Candidate generation needs a candidate-specific operation record and state model. Reusing the existing collection may be acceptable only if records remain unambiguously versioned and old records continue to parse exactly. A dedicated candidate-operation collection is the safer default.

### Explicit non-goals

This slice does not:

* make candidate revision idempotent;
* add a new public lookup route;
* add an operation dashboard;
* add cancellation;
* guarantee that an external model provider performs no duplicate computation;
* retain expired candidate mechanics forever;
* modify DungeonMindBuddy;
* change accepted statblock or immutable revision idempotency;
* change candidate quality, prompting, validation, asset behavior, or ruleset semantics.

---

## §3 Observable-path inventory

| Observable path                         | Current behavior                                         | Required behavior                                                                            | Owning boundary         |
| --------------------------------------- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------- |
| First generate request                  | Provider called; new candidate ID allocated afterward    | Durable operation and stable candidate ID reserved before provider call                      | application/persistence |
| Completed replay                        | May call provider again and create another candidate     | Return exact original candidate; zero provider calls                                         | application/route       |
| Same key, changed request               | May create a different candidate                         | Typed `409 idempotency_conflict`; zero provider calls                                        | application/route       |
| Concurrent same-key calls               | May both invoke provider and persist distinct candidates | One active lease; ordinary duplicate returns `generation_in_progress` or replays completion  | persistence/application |
| Client loses successful HTTP response   | Caller loses candidate locator                           | Repeated POST returns persisted original candidate                                           | route/integration       |
| Process exits after reservation         | No durable candidate outcome                             | Expired lease may be atomically reclaimed using the same reserved candidate ID               | persistence             |
| Worker exceeds lease and races takeover | Can duplicate work                                       | At most one candidate document becomes canonical; all successful callers resolve to it       | persistence             |
| Transaction result is indeterminate     | Caller cannot know whether commit happened               | Reconcile from durable operation record and candidate document                               | Firestore adapter       |
| Observed provider failure               | Retry semantics undefined                                | Stable terminal failure is durably replayed for the same key; new key starts a new operation | application/persistence |
| Candidate later expires                 | Replaying could accidentally regenerate                  | Return typed expired outcome; never regenerate under the same key                            | application/route       |
| Different request IDs, same body        | Independent candidates allowed                           | Distinct operations and candidate IDs                                                        | application             |
| Candidate revision                      | Non-idempotent                                           | Remains unchanged                                                                            | out of scope            |

---

## §4 Files in scope — allowlist

Expected changed paths:

| Action             | Path                                                                                  | Purpose                                                           |
| ------------------ | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Create             | `Docs/Plans/HANDOFF-pr23-statblock-v1-candidate-generate-idempotency.md`              | Canonical implementation authority                                |
| Modify             | `statblocks_v1/domain/resources.py` or one dedicated candidate-operation model module | Candidate operation state and durable outcome                     |
| Modify             | `statblocks_v1/application/repositories.py`                                           | Candidate-operation repository protocol and request digest        |
| Modify             | `statblocks_v1/application/generation.py`                                             | Reservation/replay orchestration and stable candidate ID use      |
| Modify             | `statblocks_v1/infrastructure/memory_repositories.py`                                 | Deterministic in-memory implementation                            |
| Modify             | `statblocks_v1/infrastructure/firestore_repositories.py`                              | Transactional reservation, completion, replay, and reconciliation |
| Modify             | `statblocks_v1/infrastructure/firestore_layout.md`                                    | Durable collection and document contract                          |
| Modify if required | `statblocks_v1/config.py`                                                             | Lease configuration and validation                                |
| Modify if required | `Docs/Guides/CONFIG-dungeonbuddy-statblock-v1.md`                                     | New operational setting                                           |
| Modify             | `statblocks_v1/api/dependencies.py`                                                   | Production repository/coordinator composition                     |
| Modify             | `statblocks_v1/api/http_errors.py`                                                    | Stable in-progress and conflict mappings                          |
| Modify             | `statblocks_v1/api/router.py`                                                         | Invoke idempotent generation boundary                             |
| Modify             | `openapi/dungeonbuddy-statblocks-v1.json`                                             | Published error/status contract                                   |
| Modify             | `tests/statblocks_v1/test_generation_service.py`                                      | Service replay and provider-call guarantees                       |
| Modify             | `tests/statblocks_v1/test_memory_repositories.py`                                     | State-machine and concurrency semantics                           |
| Modify             | `tests/statblocks_v1/integration/test_firestore_repositories.py`                      | Atomic transaction and indeterminate-result recovery              |
| Modify             | `tests/statblocks_v1/api/test_candidate_routes.py`                                    | HTTP replay, conflict, expiry, and lost-response proof            |
| Modify if required | `tests/statblocks_v1/test_production_composition.py`                                  | Production dependency wiring                                      |

### Bounded discovery exception

```text
Directories:
  statblocks_v1/domain
  statblocks_v1/application
  tests/statblocks_v1

Maximum additional paths:
  4

Allowed path kinds:
  one candidate-operation domain model,
  one application coordinator/service,
  and directly corresponding focused tests.

Decision rule:
  Add a path only when it is necessary to keep candidate operation state
  separate from PR15 immutable-resource idempotency.

Required report:
  Name the added path, why an allowlisted file could not own the behavior,
  and confirm that no successor capability was introduced.
```

If implementation requires changes outside this list or exception, stop and report before proceeding.

---

## §5 Explicitly out of scope

| Path or capability                           | Reason                                                       |
| -------------------------------------------- | ------------------------------------------------------------ |
| DungeonMindBuddy repository                  | Consumer adoption is a separate PR                           |
| `statblock-candidates:revise` idempotency    | Independently useful successor                               |
| New `GET .../by-request/{request_id}` route  | Not required when POST replay closes the blocker             |
| Generic operation/job framework              | Separate durable contract                                    |
| Provider-specific idempotency headers        | May be a later optimization; this capability is Server-owned |
| Candidate acceptance/create/append semantics | Already owned by PR15/PR18 contracts                         |
| UI, rendering, assets, prompt changes        | Unrelated invariant                                          |
| Administrative deletion or reset             | Separate operator capability                                 |
| Broad repository cleanup                     | Not authorized                                               |

---

## §6 Implementation contract

### Input

```text
Authenticated caller_scope
GenerateCandidateRequestV1
request_id from that request
Exact effective generation request fields:
  ruleset
  source
  intent
  context
  asset_options
  actor
```

`request_id` becomes an idempotency key for the generate operation. It is no longer correlation-only for this route.

### Request identity

The durable operation key is:

```text
caller_scope + "generate_candidate" + request_id
```

The request digest must use the existing normalized `compute_request_digest` behavior or an exactly equivalent canonical implementation.

Digest the complete caller-controlled generation intent, excluding `request_id` itself because it is already the durable key.

Do not digest transient transport metadata.

### Durable operation record

Use a candidate-specific, versioned record equivalent to:

```text
CandidateGenerationOperationV1:
  caller_scope
  operation = "generate_candidate"
  request_id
  request_digest
  candidate_id
  status = pending | completed | failed
  lease_owner
  lease_expires_at
  attempt_count
  created_at
  updated_at
  completed_at?
  failure?
```

A terminal failure snapshot must contain only stable, safe application error information needed to reproduce the same HTTP result. Do not store provider exception text or raw provider payloads.

The operation record must not embed the complete candidate payload as a substitute for the candidate repository.

### Commit model

```text
Commit point:
  Candidate document creation and operation transition to completed commit
  atomically in one Firestore transaction.

Before commit:
  The operation may be pending and recoverable.
  No candidate-generation success may be reported.

After commit:
  The request_id is permanently bound to the reserved candidate_id.
  Replays return that exact persisted candidate.

Post-commit HTTP failure:
  The client retries the same POST.
  Server reads the completed operation and returns the candidate.
```

The external provider call must not occur inside a Firestore transaction.

### First request

Atomically:

1. Validate that no operation exists for the key.
2. Allocate and persist one stable `candidate_id`.
3. Store the request digest.
4. Create a pending lease.
5. Commit the reservation before calling the provider.

Generation must use the reserved candidate ID. It must not allocate a second candidate ID after provider completion.

### Completed replay

For the same key and digest:

```text
load operation
→ load exact candidate_id
→ return exact candidate
→ do not call provider
```

### Changed-payload replay

For the same key with a different digest:

```text
409 idempotency_conflict
zero provider calls
no record mutation
no candidate mutation
```

### Active pending replay

If another worker holds a non-expired lease:

```text
409 generation_in_progress
zero provider calls
no second candidate reservation
```

Use the existing typed error envelope. A `Retry-After` header may be added when it can be calculated accurately, but it is not required for this slice.

### Expired pending recovery

A caller repeating the same request may atomically take over an expired lease.

The takeover must:

* retain the original request digest;
* retain the original reserved candidate ID;
* increment or otherwise record the attempt;
* prevent two takeover claimants from both believing they own the lease.

A takeover may call the provider again, but all attempts target the same immutable candidate ID.

This slice guarantees one persisted candidate, not exactly-once external model computation.

### Racing workers

If an older worker completes after a lease takeover:

* candidate persistence remains immutable;
* the first valid transaction to create the reserved candidate wins;
* another worker must load and return the canonical stored candidate;
* it must not overwrite candidate mechanics;
* it must not allocate another candidate ID;
* all successful responses for the request key must converge on the stored candidate.

### Observed failures

Provider refusal, incomplete output, timeout, rate limiting, validation failure, ruleset mismatch, source-digest mismatch, and safe internal generation failures must transition the operation to a terminal failed outcome when the Server has definitely observed that result.

A replay of the same key and digest returns the same stable failure without calling the provider.

A caller that intentionally wants another attempt after a terminal failure must submit a new `request_id`.

### Candidate expiration

The candidate operation record must outlive candidate TTL deletion sufficiently to prevent the same request key from silently creating a replacement candidate.

When a completed operation points to an expired or TTL-deleted candidate:

```text
return typed 410 candidate_expired or generation_replay_expired
include the exact candidate_id when the safe error envelope supports it
do not call provider
do not reset or delete the operation
```

Do not retain the full mechanics payload indefinitely merely to replay after candidate expiry.

### Transaction-indeterminate recovery

When Firestore reports an indeterminate commit:

1. Re-read the operation record.
2. Re-read the reserved candidate document.
3. Return completed candidate when both establish the committed result.
4. Return/recover pending only when the transaction definitely did not complete.
5. Fail closed on impossible identity, digest, or state combinations.

Do not report persistence failure until reconciliation has been attempted.

### Trust boundary

```text
Verifies:
  authenticated caller scope
  stable request key
  complete request digest
  operation state transitions
  candidate identity
  immutable candidate persistence
  replay/conflict semantics

Records without proving:
  generated mechanics quality
  provider determinism
  campaign correctness

Rejects:
  changed payload under the same key
  malformed operation records
  candidate IDs that differ from the reservation
  completed records without an exact candidate
  silent regeneration after expiry
```

---

## §6A State and fallback matrix

| Path                     | Initial state                               | Exact success                             | Dependency unavailable                     | Integrity failure                                   | Retry/replay            |
| ------------------------ | ------------------------------------------- | ----------------------------------------- | ------------------------------------------ | --------------------------------------------------- | ----------------------- |
| First generate           | No operation                                | Reserve ID, generate, atomically complete | Typed unavailable; preserve truthful state | Fail closed                                         | Same POST               |
| Completed replay         | Completed                                   | Return stored candidate                   | Typed unavailable; do not regenerate       | Fail closed                                         | Repeat safely           |
| Same key, changed body   | Any existing                                | N/A                                       | N/A                                        | 409 conflict                                        | New key required        |
| Active pending replay    | Pending, lease active                       | N/A                                       | N/A                                        | Fail closed if lease corrupt                        | 409 in progress         |
| Stale pending replay     | Pending, lease expired                      | Claim same reservation and continue       | Typed unavailable                          | Fail closed                                         | Same POST               |
| Terminal failure replay  | Failed                                      | Return same stable failure                | N/A                                        | Fail closed if failure record corrupt               | New key for new attempt |
| Expired candidate replay | Completed, candidate expired/missing by TTL | 410 with exact locator                    | N/A                                        | Missing before declared expiry is integrity failure | Never regenerate        |

There is no fallback to:

* a new candidate ID;
* a display-name lookup;
* the latest candidate;
* a different request record;
* a mock candidate;
* corpus content;
* an unexpired sibling candidate.

---

## §6B Identity matrix

| Situation           | Rule                                        | Ambiguity behavior                     | Fallback? | Persistence consequence                 |
| ------------------- | ------------------------------------------- | -------------------------------------- | --------- | --------------------------------------- |
| Request operation   | Exact caller scope + operation + request ID | Conflict on changed digest             | No        | Permanent operation identity            |
| Candidate           | Exact reserved `candidate_id`               | Fail closed on mismatch                | No        | One immutable candidate                 |
| Request body        | Exact canonical digest                      | 409 on mismatch                        | No        | Existing operation unchanged            |
| Concurrent worker   | Exact lease ownership/version               | Non-owner cannot commit a new identity | No        | Same candidate ID retained              |
| Candidate expiry    | Existing operation retains locator          | 410; no rebinding                      | No        | Historical request remains bound        |
| Deletion/recreation | Candidate ID cannot be rebound              | Fail closed                            | No        | Never create replacement under same key |

---

## §6C Persistence and replay matrix

| Operation                    | Durable representation                                      | Round-trip guarantee                                  | Duplicate behavior                             | Rollback/reversion                                |
| ---------------------------- | ----------------------------------------------------------- | ----------------------------------------------------- | ---------------------------------------------- | ------------------------------------------------- |
| Reserve generation           | Candidate-operation document                                | Same request key reloads same digest and candidate ID | Same digest observes existing state            | Pending may be reclaimed only through lease rules |
| Complete generation          | Candidate document + completed operation in one transaction | Replay returns exact candidate                        | Duplicate commit converges on stored candidate | Immutable after commit                            |
| Record failure               | Operation with typed terminal failure                       | Same key replays same failure                         | No provider call                               | New request ID required                           |
| Replay after process restart | Firestore operation and candidate                           | No in-memory state required                           | Exact replay                                   | No migration fallback                             |
| Candidate TTL deletion       | Operation retains candidate locator                         | Returns expired, not regenerated                      | No duplicate                                   | Candidate mechanics remain deleted                |

Compatibility policy:

* existing candidate documents remain readable;
* existing PR15 statblock/revision idempotency records remain unchanged;
* no migration of historical pre-idempotency candidate generations is required;
* idempotency applies only to requests created after this contract ships;
* no historical candidate may be retroactively claimed by request ID.

---

## §6D Predecessor-to-consumer mapping

**Grounding sources**

```text
GenerateCandidateRequestV1
GenerateStatblockCommandV1
GeneratedStatblockCandidateV1
GenerationFailureV1
CandidateRepository
PR15 compute_request_digest
current ErrorEnvelopeV1
```

| Existing field/outcome                     | Required use                                                                              |
| ------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `request.request_id`                       | Candidate generation idempotency key                                                      |
| authenticated `caller_scope`               | Namespace component of operation identity                                                 |
| ruleset/source/intent/context/assets/actor | Canonical request digest input                                                            |
| reserved `candidate_id`                    | Candidate ID used by generation and persistence                                           |
| `GeneratedStatblockCandidateV1`            | Exact replay response                                                                     |
| `GenerationFailureV1.kind`                 | Safe terminal failure code                                                                |
| `GenerationFailureV1.message`              | Safe replayable failure message only                                                      |
| provider request/response IDs              | Receipt/audit data; not operation identity                                                |
| candidate `expires_at`                     | Expired replay behavior                                                                   |
| PR15 `compute_request_digest`              | Canonical normalized digest behavior                                                      |
| `IdempotencyConflictError` vocabulary      | Reuse stable conflict semantics where appropriate without reusing the wrong outcome model |

---

## §7 Verification ownership map

| Guarantee                                     | Owning boundary                | Required proof                                                                     |
| --------------------------------------------- | ------------------------------ | ---------------------------------------------------------------------------------- |
| Same key/body returns same candidate          | route/application              | Two POSTs; equal full response; provider called once                               |
| Lost HTTP response is recoverable             | route integration              | Execute first request and discard response; second POST returns original candidate |
| Changed body conflicts                        | route/application              | Same key, changed field → 409; provider count unchanged                            |
| Concurrent duplicate does not fork candidates | repository/service concurrency | Parallel calls; one reserved candidate ID and one stored candidate                 |
| Reservation survives restart                  | repository/application         | New service instance replays pending/completed record                              |
| Expired lease takeover is safe                | repository concurrency         | Takeover retains candidate ID and converges under stale-worker race                |
| Candidate plus completion are atomic          | Firestore integration          | Failure injection and transaction-indeterminate reconciliation                     |
| Completed replay never calls provider         | application                    | Provider spy remains at original call count                                        |
| Terminal failure replays without provider     | route/application              | Same key returns same code/message; provider count unchanged                       |
| Expired candidate does not regenerate         | route/repository               | 410; exact candidate ID retained; provider count zero                              |
| Different keys remain independent             | route/application              | Same body, two keys → two candidate IDs                                            |
| PR15 idempotency is unchanged                 | regression                     | Existing create/append tests remain green                                          |
| Revise behavior remains unchanged             | route regression               | Existing candidate-revise tests remain green                                       |
| OpenAPI declares new errors                   | contract test                  | Exported schema contains 409/410 typed envelopes                                   |

### Required commands

Use repository-canonical commands where they differ, but record exact command and result.

```bash
pytest -q tests/statblocks_v1/test_generation_service.py
pytest -q tests/statblocks_v1/test_memory_repositories.py
pytest -q tests/statblocks_v1/integration/test_firestore_repositories.py
pytest -q tests/statblocks_v1/api/test_candidate_routes.py
pytest -q tests/statblocks_v1/test_production_composition.py

./scripts/run_statblocks_v1_tests.sh -q

python scripts/export_dungeonbuddy_statblock_openapi.py
git diff --check
git diff --stat 5d17e7521d086914dc67bec1f05a0c0b69547797...HEAD
git diff --name-only 5d17e7521d086914dc67bec1f05a0c0b69547797...HEAD
```

### Minimal live proof

Use the existing internal API only.

```text
1. Send generate request with request_id = req_live_replay_1.
2. Capture Server logs and candidate ID, but deliberately discard the client response.
3. Repeat the identical POST.
4. Verify the same candidate ID and definition are returned.
5. Verify only one candidate document exists.
6. Verify logs mark the second call as an idempotency replay.
7. Repeat the key with one changed request field and verify typed 409.
```

Do not build a new UI or operator surface for this proof.

---

## §8 Required implementation handback

The PR body must include:

1. Base SHA and head SHA.
2. Actual changed paths.
3. Focused diff stat.
4. Final durable operation-record schema.
5. Final Firestore collection/document key.
6. Request digest field mapping.
7. Lease duration and how it is proven longer than one normal provider execution budget.
8. Commit-point and transaction-indeterminate behavior.
9. Exact provider call counts for replay, conflict, concurrency, failure replay, and expiry tests.
10. Exact test commands and results with provenance.
11. OpenAPI fingerprint before and after.
12. Minimal live-proof request ID and candidate ID.
13. Baseline failures and explicit waivers.
14. Paths outside the allowlist.
15. Stop conditions encountered.
16. Confirmation that candidate revise remains non-idempotent.
17. Confirmation that no request-ID lookup route, cancellation API, UI, or generic job framework shipped.

---

## §9 Acceptance rubric

The reviewer accepts only when:

* [ ] The existing generate POST is safely replayable by `request_id`.
* [ ] Same key and digest return the exact persisted candidate.
* [ ] Completed replay performs zero provider calls.
* [ ] Same key with changed intent returns typed 409.
* [ ] A candidate ID is durably reserved before provider invocation.
* [ ] Provider completion uses the reserved candidate ID.
* [ ] Candidate creation and operation completion share one atomic commit point.
* [ ] A lost successful HTTP response is recovered through the repeated POST.
* [ ] Concurrent callers cannot create two candidate documents for one key.
* [ ] Expired-lease takeover retains the original candidate ID.
* [ ] A stale-worker race converges on one immutable stored candidate.
* [ ] Transaction-indeterminate outcomes are reconciled before failure is reported.
* [ ] Terminal failures replay without invoking the provider.
* [ ] Expired or TTL-deleted candidates never regenerate under the same key.
* [ ] Existing PR15 statblock/revision idempotency remains unchanged.
* [ ] Candidate revision remains outside this capability.
* [ ] The OpenAPI and typed error vocabulary match implementation.
* [ ] No unexpected path changed.
* [ ] No essential constraint exists only in chat or the PR body.

---

## §10 Reviewer protocol

Review in this order:

1. Restate the request-key invariant.
2. Inspect the durable operation model and document key.
3. Verify the candidate ID is allocated and persisted before provider invocation.
4. Verify the provider call is outside Firestore transactions.
5. Verify candidate creation and completed-state transition are atomic.
6. Trace completed replay and confirm zero provider calls.
7. Trace changed-digest conflict and confirm no mutation.
8. Trace active and expired pending states.
9. Adversarially test stale-worker completion after takeover.
10. Inject an indeterminate transaction outcome.
11. Delete or expire the candidate and ensure replay does not regenerate.
12. Confirm terminal failures are stable.
13. Confirm create/append idempotency was not weakened.
14. Confirm revision idempotency and generic job APIs did not enter the diff.
15. Compare actual paths to the allowlist.

---

## §11 Re-review protocol

Use this ledger:

| Prior blocker                                    | Required correction                                     | Verification                          |
| ------------------------------------------------ | ------------------------------------------------------- | ------------------------------------- |
| Same `request_id` may create distinct candidates | Durable request digest and stable reserved candidate ID | Same-key replay and concurrency tests |
| Buddy may lose candidate locator after timeout   | Repeated POST returns completed candidate               | Lost-response route test              |
| No request-level replay or conflict              | Completed replay plus changed-digest 409                | Route and service tests               |
| No provider-safe reservation                     | Pending lease and immutable candidate identity          | Repository concurrency tests          |
| Candidate TTL could permit silent regeneration   | Durable operation retains locator and returns 410       | Expiry test                           |

Every correction must be checked against the complete invariant, not only its changed line.

---

## Stop conditions

Stop and report if any of these are true:

* candidate creation and operation completion cannot be made atomic with the current repository boundary;
* production Firestore cannot enforce one canonical candidate ID under stale-worker races;
* lease duration cannot be safely bounded against provider execution;
* the existing generation service cannot accept a reserved candidate ID without introducing a second independently useful refactor;
* existing candidate TTL policy makes replay semantics impossible without retaining mechanics beyond approved retention;
* a generic job framework or new public lookup endpoint becomes necessary;
* PR15 idempotency records must be destructively migrated;
* implementation requires DungeonMindBuddy changes to prove Server correctness;
* a path outside the allowlist is required;
* the current main branch has moved materially from the declared base.

Use this report:

```text
Stop condition:
Why this mission cannot absorb it:
Affected observable paths:
New durable contract discovered:
Required path outside scope:
Proposed successor slice:
Operator decision required:
```

---

## Final dispatch check

* [ ] The mission is generate-request idempotency only.
* [ ] The stable candidate ID is reserved before provider work.
* [ ] The commit point is explicit.
* [ ] Replay, conflict, pending, failure, expiry, and race semantics are defined.
* [ ] Firestore and in-memory ownership are both identified.
* [ ] Verification includes lost-response and stale-worker scenarios.
* [ ] Revision idempotency remains false.
* [ ] No lookup route or generic job API is required.
* [ ] The implementation base is rechecked immediately before work begins.
* [ ] The complete handoff is checked into the Server repository before coding.
