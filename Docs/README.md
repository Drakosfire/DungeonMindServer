# DungeonMindServer Documentation

This repository owns **backend/product implementation truth** for DungeonMind Web API.

Documentation should stay close to the code whose reason to change owns it. Cross-repository architecture and sequencing belong in DungeonOverMind.

## Start here

Use the smallest authority needed:

### Current backend / platform context

- [../README.md](../README.md) — repository role and runtime shape.
- [Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md](Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md) — current startup/composition debt.
- [Plans/ANCHOR-dungeonmind-net-platform-refresh.md](Plans/ANCHOR-dungeonmind-net-platform-refresh.md) — local anchor for OverMind platform-refresh stewardship.

### DungeonBuddy statblock v1

- [Design/DESIGN-dungeonbuddy-statblock-contract-v1.md](Design/DESIGN-dungeonbuddy-statblock-contract-v1.md) — canonical product/backend contract.
- [Design/FIELD-DISPOSITION-statblockdetails-to-v1.md](Design/FIELD-DISPOSITION-statblockdetails-to-v1.md) — legacy→v1 field mapping reference.
- [Design/AUDIT-statblock-legacy-consumers.md](Design/AUDIT-statblock-legacy-consumers.md) — compatibility surfaces still known to matter.
- [Guides/CONFIG-dungeonbuddy-statblock-v1.md](Guides/CONFIG-dungeonbuddy-statblock-v1.md) — deploy/runtime configuration.
- [Runbooks/RUNBOOK-dungeonbuddy-statblock-v1.md](Runbooks/RUNBOOK-dungeonbuddy-statblock-v1.md) — smoke, rollback, operational procedure.
- [Design/GENERATION-STRUCTURED-CONFORMANCE.md](Design/GENERATION-STRUCTURED-CONFORMANCE.md) — GenerationEngine consumer-boundary guidance.
- `Design/fixtures/**` — executable contract/eval evidence.

## Audit baseline

- [Reports/REPORT-document-authority-audit-2026-09-25.md](Reports/REPORT-document-authority-audit-2026-09-25.md) — first documentation-rigor pass and placement evidence.

## Directory roles

### `Design/`

Current owner-repository architecture, product/backend contracts, live migration/compatibility audits, and executable design fixtures.

A design/audit that described how to reach a now-landed state should move to Archive instead of remaining active indefinitely.

### `Plans/`

Only active owner-repository plans/handoffs/anchors.

Completed implementation handoffs belong in Archive or Git/PR history.

### `Guides/`

Current operational/configuration guidance.

### `Runbooks/`

Current executable operational procedures.

### `Archive/`

Historical implementation context only. Archive content cannot override current code/tests/design authority.

## Authority rule

For a current behavior claim, prefer:

```text
current code/tests/schema
→ current owner design/config/runbook
→ merged PR evidence
→ archive/history
```

An open or stacked PR is proposed behavior, not current `main` authority.

## Placement rule

- server-local backend implementation/design → here;
- frontend implementation → LandingPage;
- reusable inference mechanics → GenerationEngine;
- durable world-knowledge internals → DungeonMind;
- Buddy product/orchestration → DungeonMindBuddy;
- cross-repository ownership/contracts/sequencing → DungeonOverMind.

Do not preserve stale docs merely because they once mattered.
