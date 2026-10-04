# Handoff: Managed World Agent Graph Adapter

**Status:** BLOCKED — design packet only; implementation is not activated.  
**Owner:** DungeonMindBuddy owns Agent orchestration and its runtime adapter. DungeonMindServer hosts this handoff as the cross-repository proposal; it does not grant Server ownership of Buddy code. DungeonMind owns native graph authority and read semantics. APP-STATE owns any durable receipt/provenance contract it maintains.

## Re-anchored basis

- DungeonMindServer main: `16aa604d1183b80e6675c82f6def0b1f66b05c4a`; open #28 is unrelated and does not collide with this one-file Docs/Plans proposal.
- DungeonMindBuddy authority main: `0f42fec0812655bb37c87b6be9a7fe5741d7f25f`. Relevant active work includes Agent composer #904, Plan navigation #886, and managed World/KnowledgeSpace binding #826. The #886 shell retains `PlanSurfacePage.tsx`; its test file is assigned to the mounted-harness repair worker. A future Buddy implementation must refresh these heads, path leases, and owner status before activation.
- Buddy code inspected at `707ffdfa...`; the code-level findings below must be rechecked against current main at activation.
- DungeonOverMind architecture, ownership, and contract authority were refreshed at `9a80ab328a687039519569855c2b25a4ee7df07b`.

## Primary question

Can Buddy's generic Agent graph read resolve an authorized managed World to its currently active native graph authority, preserve the caller's scoped evidence and revision pin, and retain truthful authority across replay, without changing graphless Plan Ask v1 or creating a new public API/auth contract?

## Observed defect and existing seam

In Buddy `apps/live_control_server/routes/agent.py`, `_graph_resolver` currently passes the requested managed World ID to the native graph projection as `world_id`. When managed and native IDs differ, the projection can target the wrong native authority. The existing full-route test uses equal IDs and therefore does not detect the translation defect.

Buddy already has `services/managed_world_graph_projection.py::project_managed_world_graph`. It resolves a verified managed World and active native binding, performs the graph read, rereads the binding, and rejects drift in native World ID, binding version, or source root. Reuse this authority fence; never trust client-supplied native IDs or binding versions.

The route's `graph_scope.world_id` is also used as the canonical managed World ID in turn invariants, historical references, retry, and replay. Keep that product identity managed/canonical. The current persisted Graph historical reference records managed ID and graph revision, but not native ID or binding version. Thus current replay evidence cannot establish that the same binding authority remains active.

## Required invariants for a future implementation

- Keep existing Agent route authentication and owner/saved-Plan scope checks at the boundary.
- Resolve the active native authority from the verified managed binding and use the existing before/after binding fence.
- Preserve graph query scope, campaign/focus/selection inputs where currently supported, and any requested revision pin; do not silently discard them during adaptation.
- Keep response/product ownership and turn invariants anchored to the managed World ID.
- Do not claim cross-time authority continuity if the receipt stores only managed ID and revision. The receipt owner must either define a supported binding attestation (including native ID and binding version) or define a safe invalidation/re-resolution behavior for retries and replay.
- Preserve the Plan Agent Ask v1 graphless rule: Plan surface with primary Plan requires graph request mode `none`. No graph activation for Plan Ask is part of this slice.
- Keep native graph access read-only and use fake native-owner fixtures in tests. No provider/model calls are needed to prove the adapter.

## Proposed Buddy implementation lease, pending activation

Candidate paths, subject to refreshed collision/lease review and PRIME approval:

- `apps/live_control_server/routes/agent.py`
- `apps/live_control_server/services/managed_world_graph_projection.py` only if its current request cannot preserve the Agent's supported scope and pins without changing public contracts
- `apps/live_control_server/services/agent_turn_service.py` only if the approved Buddy-owned in-memory/runtime receipt boundary requires wiring the binding attestation
- `tests/test_agent_turn_route.py`
- `tests/test_managed_world_graph_projection.py` only if the projection service changes

Do not edit APP-STATE-owned persistence or receipt files under this lease. Coordinate the receipt seam with APP-STATE and obtain its owner decision before activation. Do not edit the #886-owned Page shell or its transferred test file.

## Acceptance witness

A focused fake-owner route test must use distinct managed and native IDs, an active binding, and a pinned graph revision. It must prove the native owner receives the resolved native ID and requested pin, while the returned product scope and persisted canonical reference remain managed-ID based. Add binding drift/replay coverage for whichever receipt behavior the owners approve. Preserve regression coverage for unauthenticated access, scope denial before receipt/runtime work, malformed client authority fields, and graphless Plan Ask. Tests must not contact a provider or depend on live 5202/5203 services.

Before proposing merge readiness, inspect the cumulative diff against the exact Buddy base and run focused route/projection tests plus the repository's applicable CI gates. Record exact base/head, evidence, and the approval token only after the acceptance witness genuinely passes.

## Blockers and stop conditions

This handoff remains **BLOCKED** until all of the following are resolved:

1. APP-STATE answers whether a supported persisted receipt can carry managed owner + native owner + binding version, or specifies the safe invalidation/re-resolution rule for replay and retry. This proposal does not authorize changing APP-STATE storage.
2. PRIME approves the precise cross-time evidence behavior and activates a Buddy-owned code lease after a fresh PR/path collision check, including current #826 binding changes and #904/#886 ownership.
3. The adapter request mapping is pinned down for currently supported campaign/focus/selection fields and revision semantics, with an owner-level test witness.

Stop and return to PRIME if the accepted receipt behavior requires a new cross-owner/public contract or a separate APP-STATE implementation slice. Do not expand into Plan Graph activation, new authentication framework or public API schema, database migration, DungeonMind graph writes, provider execution, or runtime operation.

## Operational limits

Do not restart or modify the UI on 5202, API on 8000, or DOGFOOD on 5203. Do not modify operator credentials or private corpus state. Any future fixture must use an isolated test client/port and must not use 5202.