# Audit: Legacy StatBlockGenerator Consumer Inventory

**Status:** ACTIVE — post-launch compatibility inventory  
**Last verified:** 2026-07-17  
**Scope:** legacy `/api/statblockgenerator/*` routes and historical command-board v2 routes.  
**Traffic evidence:** no production telemetry was available in this repository; statuses below are source and test evidence, not usage-volume claims.

## Findings

| Surface | Status | Evidence | Disposition |
| --- | --- | --- | --- |
| `POST /generate-statblock` | **Active** | LandingPage calls it in `src/components/StatBlockGenerator/steps/Step1CreatureDescription.tsx` and `statblockEngineConfig.ts`; `GenerationDrawerDemo.tsx` and benchmark script also reference it. Server auth tests assert it remains outside the DungeonBuddy internal-key gate. | Preserve unchanged. |
| `GET /v2/health` | **Active** | `DungeonMindBuddy/src/statblocks/v2_client.py` calls the route; Buddy client and contract tests assert the path and `supports` payload. | Preserve as historical v2 compatibility. |
| `POST /v2/generate-draft` | **Active** | `DungeonMindBuddy/src/statblocks/v2_client.py` calls it; Buddy tests, lifecycle design, and production-deploy report exercise it. | Preserve as historical v2 compatibility. |
| `POST /v2/render-draft` | **Active** | `DungeonMindBuddy/src/statblocks/v2_client.py` calls it; Buddy tests and deploy report exercise the round trip. | Preserve as historical v2 compatibility. |
| Project routes (`create-project`, `list-projects`, `project/{id}`, `save-project`, deletion) | **Active** | LandingPage `StatBlockGeneratorProvider.tsx` calls save, list, fetch, and image-removal project paths. | Preserve unchanged. |
| Image routes (`upload-image`, `upload-images`, `list-all-images`, `delete-image`, project image deletion) | **Active** | LandingPage `GenerationDrawerDemo.tsx` references upload, delete, and library routes; `tests/test_image_upload.py` targets `upload-images`; provider calls project image deletion. | Preserve unchanged. |
| Session routes (`save-session`, `load-session/{id}`) | **Unknown** | Implemented in the server and described in the legacy command-board audit, but no current LandingPage or DungeonBuddy call-site was found by repository search. | Retain pending production telemetry or a targeted client audit. |
| Legacy validation and CR routes | **Active** | LandingPage `StatBlockGeneratorProvider.tsx` calls `validate-statblock` and `calculate-cr`. | Preserve unchanged. |

## Boundary decision

`statblocks_v1` is the active DungeonBuddy authority. The v2 command-board routes are still active compatibility surfaces for confirmed Buddy consumers, but their original design/audit/handoff documents are historical implementation evidence. The legacy app router remains mounted for confirmed LandingPage consumers.

No route is deleted or response shape changed by this audit.
