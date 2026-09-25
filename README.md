# DungeonMind Web API

DungeonMindServer is the **public backend / BFF for dungeonmind.net**.

It is a modular FastAPI application that owns public product APIs, authentication/session behavior, authorization/quotas, product workflow composition, and backend persistence for the web product.

It is not the owner of:

- frontend state/presentation — `LandingPage` / DungeonMind Web;
- reusable inference execution — `GenerationEngine`;
- durable governed world knowledge — `DungeonMind`;
- DungeonBuddy product semantics/orchestration — `DungeonMindBuddy`.

## Runtime shape

This repository is a **modular monolith**, not a collection of independently deployed backend microservices.

Current feature modules include:

- authentication/session infrastructure;
- CardGenerator;
- StatBlockGenerator and the newer `statblocks_v1` bounded context;
- Rules Lawyer / Rules-As-Guide;
- StoreGenerator;
- PlayerCharacterGenerator backend support;
- asset/image integration;
- other compatibility and product routes composed by the FastAPI app.

Extract a separately deployed service only when a concrete operational reason exists.

## Documentation

Start at [Docs/README.md](Docs/README.md).

Current high-value authority includes:

- `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md` — current DungeonBuddy statblock contract owned by this server;
- `Docs/Guides/CONFIG-dungeonbuddy-statblock-v1.md` — operational configuration;
- `Docs/Runbooks/RUNBOOK-dungeonbuddy-statblock-v1.md` — deployment/rollback/smoke procedure;
- `Docs/Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md` — current server composition/startup debt;
- `Docs/Plans/ANCHOR-dungeonmind-net-platform-refresh.md` — local anchor for the cross-repository platform-refresh stewardship lane.

Executable contract fixtures under `Docs/Design/fixtures/` are evidence, not generic prose documentation; keep them aligned with the owning schema/tests.

## Cross-repository architecture

DungeonOverMind owns ecosystem architecture, repository ownership, contract topology, and cross-repository sequencing.

Current platform-refresh architecture/reconnaissance lives there. This repository owns implementation once a bounded Server slice is dispatched here.

## Development

Use the committed `uv.lock` for reproducible environments.

```bash
uv sync --locked
uv run pytest
```

The focused statblock-v1 lane also has repository scripts/tests documented by its config and runbook.

## Current caution

Open statblock PRs may contain branch-only contract evolution. Treat `main` plus merged PR evidence as current repository authority; do not update active docs to describe a stacked/open branch as shipped behavior.
