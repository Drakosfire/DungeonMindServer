# Anchor — DungeonMind.net Platform Refresh

**Status:** ACTIVE REFERENCE / NO IMPLEMENTATION DISPATCH  
**Created:** 2026-09-25  
**Cross-repository authority:** `Drakosfire/DungeonOverMind/Docs/roadmaps/ROADMAP-dungeonmind-net-platform-refresh.md`  
**Steward handoff:** `Drakosfire/DungeonOverMind/Docs/Plans/STEWARDS-HANDOFF-dungeonmind-net-platform-refresh.md`

## Why this exists

DungeonBuddy's eventual production launch on `dungeonmind.net` is being used as an opportunity to reassess the public DungeonMind platform, including this server's composition, storage, sessions, deployment, and legacy cleanup.

This repository remains the implementation owner for public web backend/BFF behavior.

OverMind owns the cross-repository platform-refresh architecture and sequencing.

## Current working questions for this repository

The steward will deeper-audit:

- FastAPI application composition and import-time lifecycle;
- Google OAuth/session behavior;
- in-memory `EnhancedGlobalSessionManager` authority and restart semantics;
- account/world authorization;
- Firestore consumers and migration pressure;
- MongoDB consumers and whether they earn continued separate storage;
- Cloudflare Images/R2 asset boundaries;
- statblock/image capability reuse by Buddy;
- legacy/compatibility routers;
- GenerationEngine/direct-provider boundaries;
- Docker/uv-lock reproducibility;
- health/readiness, backups, deploy and rollback posture.

## Working direction — not yet implementation authority

Likely principles to test:

- remain a modular monolith unless real operational pressure justifies extraction;
- do not put website user/account semantics into DungeonMind;
- prefer PostgreSQL for new relational platform state unless another store has a concrete reason to exist;
- do not bulk-migrate Firestore/Mongo for aesthetic consistency;
- retain Cloudflare object/CDN storage where it is earning its complexity;
- move product-critical authority out of process memory;
- clean up only when it simplifies/safens the live production path or removes a replaced path.

## Scope guard

This anchor authorizes no code by itself.

Current statblock work and other owner-repository lanes continue under their existing handoffs.

When the platform steward dispatches a server slice, the complete implementation handoff will be checked into this repository and will own its exact file lease/evidence.
