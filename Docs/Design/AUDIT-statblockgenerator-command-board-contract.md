# AUDIT: StatBlockGenerator producer contract for DungeonBuddy command-board integration

## Purpose

This audit captures the current StatBlockGenerator producer surface and the contract gaps that matter before DungeonBuddy treats it as a command-board dependency. It is intentionally documentation + fixtures + gap analysis only: no API rewrite, no DungeonBuddy client, no corpus promotion, and no generator workflow UI changes are included in this PR.

## Executive summary

DungeonBuddy can call the existing StatBlockGenerator API today, but only for description-first generation through the current app-facing endpoint. The current response is useful for the existing generator workflow, but it is not a stable draft envelope for external consumers that need provenance, markdown, parsed combat defaults, lifecycle/review state, source references, terrain pressure, and accept-to-combat semantics.

Recommended next step: add a versioned draft contract beside the current router, for example `POST /api/statblockgenerator/v2/generate-draft`, and wrap the existing `StatBlockDetails` generation core with adapter request/response models.

## Current producer surface

### Existing router prefix and endpoints

The StatBlockGenerator FastAPI router is mounted under `APIRouter(prefix="/api/statblockgenerator", tags=["statblockgenerator"])`. Current endpoints include:

| Method | Path | Current role | Command-board relevance |
| --- | --- | --- | --- |
| `GET` | `/api/statblockgenerator/health` | Service health. There are currently two route definitions for `/health` in the router, returning different payload shapes. | Useful, but should be normalized for an external contract. |
| `POST` | `/api/statblockgenerator/generate-statblock` | Description-first statblock generation. Anonymous access is allowed. | Useful generation core, but request/response shape is not enough for DungeonBuddy. |
| `POST` | `/api/statblockgenerator/validate-statblock` | Validates a `StatBlockDetails` payload with basic or strict validation. | Useful review primitive, but not a review lifecycle envelope. |
| `POST` | `/api/statblockgenerator/calculate-cr` | Calculates simplified CR analysis from a `StatBlockDetails` payload. | Useful for warnings/defaults, but insufficient alone. |
| `POST` | `/api/statblockgenerator/upload-image` | Uploads one image for authenticated users. | Not required for command-board draft generation. |
| `POST` | `/api/statblockgenerator/upload-images` | Uploads many images for authenticated users. | Not required for command-board draft generation. |
| `POST` | `/api/statblockgenerator/create-project` | Creates a persisted StatBlock project. | Separate from live-use combat drafts. |
| `GET` | `/api/statblockgenerator/list-projects` | Lists user projects. | Separate from live-use combat drafts. |
| `GET` | `/api/statblockgenerator/list-all-images` | Lists generated/uploaded images. | Not required for command-board draft generation. |
| `GET` | `/api/statblockgenerator/project/{project_id}` | Loads a saved project. | Potential source for revision, not the first contract. |
| `DELETE` | `/api/statblockgenerator/project/{project_id}/image/{image_id}` | Removes a project image. | Out of scope. |
| `DELETE` | `/api/statblockgenerator/delete-image` | Removes an image. | Out of scope. |
| `DELETE` | `/api/statblockgenerator/project/{project_id}` | Deletes a project. | Out of scope. |
| `POST` | `/api/statblockgenerator/save-project` | Saves a project and normalizes IDs in nested list objects. | Corpus/project storage, not live accept-to-combat. |
| `POST` | `/api/statblockgenerator/save-session` | Persists generator session state. | UI/session persistence, not a producer draft contract. |
| `GET` | `/api/statblockgenerator/load-session/{session_id}` | Loads generator session state. | UI/session persistence, not a producer draft contract. |

### Existing generation request shape

`POST /api/statblockgenerator/generate-statblock` accepts `CreatureGenerationRequest`:

```json
{
  "description": "Natural language creature description",
  "includeSpellcasting": false,
  "includeLegendaryActions": false,
  "includeLairActions": false,
  "challenge_rating_target": "optional CR target"
}
```

The model also accepts snake_case aliases for the boolean fields. The important producer-contract point is that `description` is required and primary; source statblocks, encounter state, terrain pressure, provenance, and review intent are not first-class request fields.

### Existing generation response shape

The router wraps successful generation responses as:

```json
{
  "success": true,
  "data": {
    "statblock": { "...": "StatBlockDetails serialized with camelCase aliases" },
    "generation_info": {
      "prompt_version": "...",
      "model_used": "gpt-4o-2024-08-06",
      "generation_time": "ISO timestamp",
      "structured_outputs": true
    }
  },
  "timestamp": "ISO timestamp",
  "generation_time_seconds": 0.0
}
```

This is an app endpoint response rather than a stable producer draft envelope. It does not name draft lifecycle state, source references, markdown, combat defaults, consumer warnings, or accept-to-combat guidance.

### Existing request/response models

Current useful models:

- `StatBlockDetails`: complete D&D 5e creature statblock with camelCase aliases, combat fields, actions, spellcasting, legendary actions, lair actions, descriptive text, image prompt, project integration metadata, and CR validation.
- `CreatureGenerationRequest`: description-first generation request with spellcasting, legendary, lair, and target CR options.
- `StatBlockValidationRequest`: validation wrapper around `StatBlockDetails` plus `strict_validation`.
- `ProjectCreateRequest`, `SessionSaveRequest`, and generator state/project models: valuable for the existing app workflow, but not a command-board producer contract.

### Existing tests

The existing statblock tests already cover useful primitives:

- Prompt construction for basic generation, spellcasting/legendary options, validation prompts, and CR prompts.
- Pydantic validation and schema generation for `StatBlockDetails` and related nested models.
- Ability modifier calculation and CR value validation.
- Generator initialization with and without OpenAI configuration.
- Graceful failure when OpenAI is unavailable.
- Successful structured-output generation through a mocked OpenAI call.
- OpenAI refusal handling.
- Basic CR calculation and proficiency bonus calculation.
- Integration-style generation/validation workflow with mocked output.
- Project save normalization and pages API coverage in adjacent test files.

### Existing validation and CR limits

Current validation is a helpful start but not the DungeonBuddy legality/review envelope:

- Pydantic validates field types, basic numeric ranges, enum values, and CR string/fraction formats.
- `validate_statblock` performs basic checks for ability ranges, expected proficiency bonus, hit-points-vs-hit-dice consistency, passive Perception, and a simplified calculated CR.
- `calculate_challenge_rating` uses a simplified HP/AC/offense heuristic and can include AI analysis when configured.
- Strict validation can call the LLM, but the result is not currently normalized into typed legality findings, severity levels, or an explicit review status.

## DungeonBuddy consumer needs

DungeonBuddy command-board integration needs StatBlockGenerator to behave like a producer of live combat drafts, not only as a generator app backend.

### Generate from source statblock

DungeonBuddy should be able to send a source statblock or partial statblock, source references, and a desired transformation. Example use cases:

- Create a tripod variant from an existing construct statblock.
- Reskin a creature while preserving AC/HP/action economy.
- Generate a battlefield-ready enemy from a lore snippet plus existing creature defaults.

### Revise existing statblock

DungeonBuddy should be able to submit a draft or existing statblock with revision instructions:

- Make this creature weaker for a depleted party.
- Reduce action complexity for a fast-running encounter.
- Keep identity and tactics while changing CR band.

### Generate quick reinforcement from combat context

The command board may need a quick reinforcement during an active encounter. The request should support:

- Party level/size and active condition summary.
- Round number, current threat pressure, and encounter objective.
- Desired arrival vector and tactical role.
- Constraints such as "dies in one or two hits" or "controller, not striker".

### Include terrain pressure

Terrain should be a first-class context input, not prose hidden inside `description`. DungeonBuddy needs to communicate pressure such as:

- Choke points, elevation, water, carts, doors, hazards, difficult terrain, light level, cover, and escape routes.
- Terrain-driven desired actions, reactions, or movement constraints.
- Warnings when generated abilities ignore the terrain premise.

### Return markdown, parsed combat defaults, warnings, provenance, and review status

A command-board response should be directly usable by the DM without frontend-only interpretation. It should return:

- `markdown`: stable rendered statblock text for display/copy/paste.
- `statblock`: full `StatBlockDetails` JSON for structured consumers.
- `combat_defaults`: initiative bonus, passive Perception, AC, HP, speed summary, primary attacks, save DCs, damage expectations, condition immunities, senses, and suggested tactics.
- `warnings`: typed warnings with severity, field references, and remediation notes.
- `provenance`: generation mode, model, prompt/schema version, source references, requested changes, and timestamps.
- `review`: lifecycle state such as `live_draft`, `reviewed`, or `corpus_candidate`.

### Support accept-to-combat without corpus write

DungeonBuddy should be able to accept a generated draft into the active combat tracker without forcing a StatBlockGenerator project save or corpus promotion. Durable corpus/project storage can be added later as a separate workflow.

## Contract gaps

1. **Current request is description-first, not context-bundle-first.** The current required field is `description`; combat context, source statblocks, source references, terrain, target role, and revision instructions have no typed home.
2. **Current response is `success` / `data` / `timestamp`, not a stable draft envelope.** The response does not provide a named draft ID, lifecycle state, or consumer-safe shape.
3. **No explicit provenance/sourceRefs.** The only provenance-like fields are prompt version, model name, generation time, and structured-output flag.
4. **No generated markdown output contract.** Markdown is not returned as an API field, so each frontend/client would need to render independently.
5. **No parsed combat defaults contract separate from full statblock JSON.** Consumers must derive initiative, attack summaries, save DCs, tactics, and encounter-ready fields themselves.
6. **No distinction between live-use draft, reviewed draft, and corpus-promotable artifact.** Generated statblocks and persisted projects/sessions are not modeled as separate lifecycle stages.
7. **Existing validation exists but is not the legality/review envelope DungeonBuddy needs.** Warnings/errors are plain lists, and strict AI analysis is free text when present.
8. **Existing endpoints are useful, but not yet a versioned external consumer API.** They are primarily app/workflow endpoints under the StatBlockGenerator router.
9. **`/health` currently has duplicate route definitions.** Before an external contract relies on health responses, the router should expose one canonical health payload.

## Recommended API contract v0

### Design decision

Document both options, but choose **Option A for the next implementation PR** unless the repository already establishes a stronger convention for service-boundary APIs.

#### Option A: v2 producer API beside current app API (recommended first)

Example endpoints under the existing router:

- `POST /api/statblockgenerator/v2/generate-draft`
- `POST /api/statblockgenerator/v2/revise-draft`
- `POST /api/statblockgenerator/v2/parse-draft`
- `GET /api/statblockgenerator/v2/health`

Why this is recommended first:

- Least disruptive to existing `/api/statblockgenerator/generate-statblock` consumers.
- Makes clear the new contract belongs to StatBlockGenerator, while separating app endpoints from producer draft endpoints.
- Allows the implementation to wrap the current generation core and reuse `StatBlockDetails`.
- Leaves room to alias or rename later if the service boundary hardens.

#### Option B: new generic statblocks API

Example endpoints:

- `POST /api/statblocks/generate`
- `POST /api/statblocks/revise`
- `POST /api/statblocks/parse`
- `GET /api/statblocks/health`

Why this may be cleaner later:

- Presents a consumer-oriented service boundary to DungeonBuddy.
- Avoids tying the long-term contract name to the generator app implementation.
- Could eventually include non-generator statblock operations.

Why not choose it in the first implementation PR:

- It is a broader routing/service-boundary decision.
- It risks implying a larger API migration before the draft contract is proven.

### Proposed v0 request envelope

```json
{
  "request_id": "db-cmd-2026-06-08T12:00:00Z-001",
  "mode": "generate_from_prompt | generate_from_source_statblock | revise_existing | quick_reinforcement | terrain_pressure",
  "intent": {
    "summary": "Short DM-facing goal",
    "target_cr": "2",
    "target_role": "controller",
    "tone": "grim swamp horror",
    "complexity": "low | medium | high"
  },
  "prompt": "Optional freeform generation prompt",
  "source_statblock": { "...": "Optional StatBlockDetails or partial statblock" },
  "revision_instructions": ["Optional list of requested changes"],
  "encounter_context": {
    "party_level": 4,
    "party_size": 5,
    "round": 3,
    "threat_pressure": "medium",
    "objective": "hold the gate for two more rounds"
  },
  "terrain_context": {
    "summary": "Optional terrain summary",
    "features": ["cart jam", "mud", "half cover"],
    "hazards": ["burning oil"],
    "constraints": ["large creatures cannot pass the gate"]
  },
  "source_refs": [
    {
      "id": "encounter:mireward-gate",
      "kind": "encounter",
      "label": "Mireward Gate encounter note"
    }
  ],
  "output_options": {
    "include_markdown": true,
    "include_combat_defaults": true,
    "include_review_warnings": true,
    "persist": false
  }
}
```

### Proposed v0 response envelope

```json
{
  "success": true,
  "draft": {
    "draft_id": "sbg-draft-...",
    "lifecycle_state": "live_draft",
    "review_status": "needs_dm_review",
    "statblock": { "...": "StatBlockDetails serialized with aliases" },
    "markdown": "Rendered statblock markdown",
    "combat_defaults": {
      "name": "Cart-Jam Harrier",
      "armor_class": 13,
      "hit_points": 22,
      "initiative_bonus": 2,
      "passive_perception": 11,
      "speed_summary": "30 ft.",
      "primary_actions": ["Hooked Spear", "Shove Cart"],
      "save_dcs": [],
      "suggested_tactics": ["Block the lane", "Use carts as half cover"]
    },
    "warnings": [
      {
        "severity": "review",
        "code": "terrain_assumption",
        "message": "Generated shove action assumes unsecured carts.",
        "field": "actions[1]"
      }
    ],
    "provenance": {
      "mode": "terrain_pressure",
      "source_refs": ["encounter:mireward-gate"],
      "prompt_version": "...",
      "model_used": "...",
      "generated_at": "ISO timestamp"
    }
  },
  "timestamp": "ISO timestamp"
}
```

## Fixture pack

Fixtures live under `Docs/Design/fixtures/statblockgenerator-command-board-contract/` and model the desired v2 request envelope rather than the current `generate-statblock` shape.

| Fixture | Workflow covered |
| --- | --- |
| `generate_from_prompt.basic.json` | Basic prompt-driven draft generation. |
| `generate_from_source_statblock.tripod_variant.json` | Variant generation from a source statblock and source reference. |
| `revise_existing.latch_harrow_weaker.json` | Revision of an existing statblock to reduce difficulty. |
| `quick_reinforcement.mireward_gate.json` | Active-combat reinforcement generation from encounter context. |
| `terrain_pressure.cart_jam_controller.json` | Terrain-informed controller generation. |

## Implementation recommendation

For PR A1.1:

1. Do not replace `POST /api/statblockgenerator/generate-statblock`.
2. Add v2 producer-facing routes under the existing router first.
3. Add request/response adapter models instead of contorting the current app endpoint.
4. Reuse `StatBlockDetails` as the full structured statblock payload.
5. Add explicit markdown rendering/export as a contract field.
6. Add explicit `combat_defaults` extraction separate from the full statblock JSON.
7. Add typed warnings and review lifecycle state.
8. Keep `persist: false` as the default for command-board drafts so accept-to-combat does not write to the corpus/project store.
9. Consider consolidating the duplicate `/health` routes before or during v2 health implementation.

## Not in PR 1

- Do not build the DungeonBuddy client yet.
- Do not add corpus promotion yet.
- Do not revise the full generator workflow UI.
- Do not remove or rewrite `/api/statblockgenerator/generate-statblock`.

## Acceptance checklist answered

- **Can DungeonBuddy call the existing API today?** Yes, but only for description-first generation through `POST /api/statblockgenerator/generate-statblock`.
- **What shape does the current generator return?** `success`, `data`, `timestamp`, and `generation_time_seconds`; `data` includes `statblock` and `generation_info`.
- **What is missing for command-board consumption?** Context references, provenance, markdown, parsed combat defaults, review warnings, lifecycle state, terrain context, and accept-to-combat semantics.
- **What endpoint shape should the next PR implement?** A versioned draft-generation endpoint wrapping the existing core, preferably `POST /api/statblockgenerator/v2/generate-draft` first.
- **What fixtures prove the desired use cases?** The fixture pack contains five JSON request envelopes mapped directly to DungeonBuddy workflows.
