# Agent operating policy

This is the durable repository guidance for agents working in DungeonMindServer, the public `dungeonmind.net` backend (DungeonMind Web API). Keep slice-specific scope, predecessors, and acceptance evidence in the relevant HANDOFF, not in this file.

## Ecosystem execution core — overmind-agent-core-v1

These rules are intentionally shared across active DungeonMind ecosystem repositories. Repository-specific law may add constraints, but it must not weaken this core.

1. **Re-anchor before action.** Fetch the current remote default branch and inspect relevant open PRs/active work before editing, reviewing, or merging. Chat history, stale handoffs, and local `main` are not current authority.
2. **Respect ownership boundaries.** Cross-repository architecture and sequencing belong in DungeonOverMind; runtime/product implementation belongs in the repository that owns the capability. When a change crosses owners, name the contract.
3. **Handoffs are portable bounded contracts.** A handoff may live on `main`, a branch, a PR, or another durable pinned ref/location. Its location alone neither activates nor invalidates it. Execution authority comes from explicit authorization/status, a pinned authority/ref, and bounded scope/write ownership. Do not require a handoff to be merged to `main` unless the specific workstream explicitly makes that a gate.
4. **Finish authorized implementation work all the way to a PR.** Once implementation is authorized, ordinary completion includes: implement → test/verify → inspect the cumulative diff → commit intended changes → push the branch → open or update the assigned PR. If no PR exists, open it. Do not stop with intended work only local, uncommitted, or unpushed and wait for another prompt to commit/push/open the PR.
5. **Merge is separate authority.** Opening/updating a PR is part of implementation completion; merging it is not. Merge only when the user or the repository's explicit process authorizes merge.
6. **Use isolated Git lanes.** Do not develop on local `main`. Use a branch/worktree or equivalent isolated checkout, and treat file/runtime/state collisions as coordination problems rather than relying on Git conflicts.
7. **Keep slices bounded.** One implementation slice should deliver one independently useful capability. A second capability, new durable/public contract, or unplanned extra PR is a stop/split signal unless explicitly authorized.
8. **Verify at the owning boundary.** Review the exact cumulative base→head diff and prove behavior at the layer that owns the invariant. A green helper test is not evidence for a boundary it does not exercise.
9. **Settle after merge.** Re-anchor, synchronize mutable authority that now became stale, and prune superseded process/transition scaffolding. Git history is the default archive; preserve a separate archive copy only when it carries unique durable evidence.

## Authority and re-anchoring

1. Read the current checkout, its active HANDOFF (if any), and the relevant code and tests before changing behavior. Re-check the remote base and open work when preparing a PR or activating a dependent slice. Chat history and old plans are context, not current authority.
2. For cross-repository ownership and contracts, use DungeonOverMind's active `Docs/architecture/ARCHITECTURE-dungeonmind-ecosystem.md`, `REPOSITORY-OWNERSHIP.md`, `CONTRACT-MAP.md`, and ecosystem roadmap, in that order. Its `.cursor/rules/QUICK-REFERENCE-DungeonMind.mdc` summarizes the boundaries. Older monorepo or microservice descriptions lose when they conflict with these authorities.
3. For current server behavior, follow `Docs/README.md`: current code/tests/schema, then current owner design/config/runbook, then merged PR evidence. Archived handoffs are history; an open PR is proposed behavior. Use `README.md`, `pyproject.toml`, the committed `uv.lock`, and current implementation handoffs for local workflow. Do not infer implementation details from ecosystem diagrams.

## Ownership boundaries

- DungeonMindServer owns public product auth and sessions, users/projects, product APIs, quotas, product persistence, and public generator/tool workflows. It remains a modular FastAPI application unless an actual operational reason justifies extraction.
- LandingPage owns the public frontend. The crossing seam is the product Web API contract: prefer FastAPI/Pydantic → OpenAPI → generated or validated TypeScript types where practical. Do not expose Firestore records, provider SDK objects, or backend module layout as frontend contracts.
- GenerationEngine owns reusable provider/model execution, capabilities, retries/timeouts, and usage/cost/latency normalization. This repository owns product prompts, validation, authorization, and its mapping from product actions to generic inference requirements. Do not add new reusable provider plumbing here.
- DungeonMind owns governed durable knowledge, evidence, publication, retrieval semantics, and persistence. This server is not a universal gateway to the kernel. Add a controlled query consumer only when a real public product use case requires it; do not copy kernel internals.
- DungeonMindBuddy owns its GM workbench and Agent orchestration. RulesIngestion and RulesEngine own their own rules pipeline and evaluator work. Do not absorb their contracts or implementation into this repository merely because legacy routes or directories use similar names.
- DungeonOverMind is a non-runtime control plane. Production code must not import or read its configuration.

If a change crosses two ownership domains, name the contract transition and its owner. If it crosses three or more, inspect the design before implementation.

## Slice and PR discipline

1. Make one independently useful, reviewable capability per implementation slice. Record the primary invariant, predecessor, intended write paths, exclusions, stop conditions, and acceptance witness in its HANDOFF when the workstream uses handoffs.
2. A planned or `BLOCKED` handoff is design authority, not an implementation lease. Re-anchor and record the activation facts before treating it as `ACTIVE`. A draft PR shell containing only a handoff does not authorize implementation or merge by itself.
3. An `ACTIVE` handoff's path list is its expected write lease. Keep changes inside it. A needed path outside the lease, a new public contract, or a second independent capability is a stop and re-scope signal.
4. Use an isolated branch or worktree for implementation. Stacked or parallel PRs require an explicit topology and predecessor/base relationship in the handoff; otherwise work serially. Check shared runtime state (ports, databases, caches, generated files) as well as file overlap before concurrent work.
5. Review the cumulative diff against the intended base, not just the latest commit. Keep unrelated changes and inherited work out of the PR. Preserve existing uncommitted user work.
6. After a merge, synchronize mutable plans, trackers, and handoffs that claim current state. Record completed facts only; do not pre-mark an in-flight slice done or invent its future merge evidence.

## Engineering evidence

- Validate behavior at the owning boundary: domain tests for pure logic; API/auth/persistence tests for public behavior; contract or seam checks for cross-repository changes. Run the relevant tests and report their actual results. A helper test alone cannot prove an endpoint or persistence invariant.
- Start debugging from observed behavior and a falsifiable hypothesis. Preserve failure details, trace the cause to the owning layer, and verify the fix against the original symptom.
- Keep auth and resource ownership checks at API boundaries. Do not log secrets, credentials, session material, or unredacted user content.
- Keep changes modular and deterministic where the contract requires reproducibility. Isolate external IO and model calls, and make failure states explicit.
- Update architecture or API documentation when its claims actually change. Avoid ceremonial rewrites of stable authority files.

## Local working notes

- The package is `dungeonmind-web-api` (Python 3.11+). Use `uv sync --locked` and the narrowest relevant `uv run pytest` target; `.github/workflows/` is the source for CI gates.
- The shared `@RTK.md` guidance concerns token-efficient CLI output. Use it where available without losing error, test, or review evidence.
