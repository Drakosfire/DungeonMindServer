# DungeonMindServer documentation archive — 2026-09-25

**Status:** HISTORICAL IMPLEMENTATION / TRANSITION EVIDENCE  
**Current documentation index:** `Docs/README.md`

This archive bundle removes completed statblock transition plans and predecessor audits from active context without deleting their evidence.

## Statblock v1 transition

The PR12–PR26 implementation handoffs and original route roadmap are complete historical evidence.

Merged mainline milestones verified from GitHub:

| PR | Outcome | Merge commit |
|---:|---|---|
| 12 | bounded-context foundation | `32885c19bb89e8c861df082d2057cded8515034c` |
| 13 | contract models / fixtures | `faf9cf40978075559da1f79c4aba706e1037c53c` |
| 14 | canonicalization / validation / digest | `f9a5cc741204ada50d3ab35b6107ef2869688081` |
| 15 | repositories / immutable persistence | `38ed3dfec0ac354d0ced5c3e8fbdc23480cede0a` |
| 16 | structured generation service | `5516ede2ad44d288defa453239aabcd3689bf943` |
| 17 | candidate API | `78a36774083f0f435b599e9ec08cdb4a1d965657` |
| 18 | revision resource API | `04b6b2d39bb838b4b09a47ba771437cfcf60c1a1` |
| 19 | assets/OpenAPI/consumer contract | `40a94c5dcd0349f9499a76ae9b346a2a9f3d16b9` |
| 20 | production hardening / launch readiness | `67ac76f11da91753edbcf2592a41ff4ff9e17e10` |
| 21 | legacy quarantine / repo hygiene | `f01670e19b595f54463c0ae9835cb4501300c079` |
| 23 | generate idempotency | `af0096a27d7f0134d052450d528d90bb4235162c` |
| 24 | revise idempotency | `2c7d2566baa744f2b1a4667761775c1dec87a2d4` |
| 26 | prompt/schema guidance | `c0c8980472b9527642b49fc9d9e7aab2e0135d8f` |

PR27 was merged onto a divergent feature branch rather than Server `main`; PR28 remains open on that stacked branch. PR29 is also open/divergent. Do not treat those branch states as shipped mainline behavior.

## Archived predecessor material

Also moved here:

- original route-readiness architecture audit;
- predecessor StatBlockGenerator command-board/v2 contract audit;
- v2 draft producer handoff;
- v2 internal API-key hardening handoff.

The v2 routes remain compatibility surfaces only where current consumer evidence says so. Current compatibility authority is `Docs/Design/AUDIT-statblock-legacy-consumers.md`.

## Current authority

Do not resume work from archived handoffs.

Use:

- `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md`;
- `Docs/Design/AUDIT-statblock-legacy-consumers.md`;
- `Docs/Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md`;
- `Docs/Guides/CONFIG-dungeonbuddy-statblock-v1.md`;
- `Docs/Runbooks/RUNBOOK-dungeonbuddy-statblock-v1.md`;
- current code/tests/OpenAPI artifacts.

Open PRs remain proposal/review evidence until merged into `main`.
