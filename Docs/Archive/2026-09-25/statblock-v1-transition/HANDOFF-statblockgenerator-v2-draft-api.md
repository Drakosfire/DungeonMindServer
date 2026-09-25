# HANDOFF — StatBlockGenerator v2 draft API

> **Historical / superseded for DungeonBuddy:** This implementation handoff is complete
> predecessor evidence. The active authority is
> `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md`; v2 remains mounted only
> for confirmed compatibility consumers.

**Created:** 2026-06-08  
**Repo:** `Drakosfire/DungeonMindServer`  
**Target base branch:** `main`  
**Depends on:** PR #8 / `092d6ff9e6d45036896974025bfa253b8a281884` — Audit StatBlockGenerator command-board contract  
**Suggested next branch:** `codex/statblockgenerator-v2-draft-api`  
**Mode:** Implementation handoff for a narrow producer-contract PR. Do not build DungeonBuddy client code in this slice.

---

## 0. Re-anchor

The DungeonBuddy command-board vision needs StatBlockGenerator to behave as a **producer of reviewed live-combat statblock drafts**, not only as a full generator app backend.

The desired cross-product flow is:

```text
DungeonBuddy Combat Pane / Statblock View
→ request a statblock draft from DungeonMindServer StatBlockGenerator
→ receive markdown + structured statblock + combat defaults + provenance + warnings
→ review/edit in DungeonBuddy
→ accept into combat as live state
→ later, optionally promote to corpus through DungeonBuddy's separate safe write path
```

PR #8 established the audit and fixture baseline. It confirmed:

- Existing app endpoint: `POST /api/statblockgenerator/generate-statblock`.
- Existing core model: `StatBlockDetails`.
- Existing generator core: `StatBlockGenerator.generate_creature()`.
- Existing validation/CR helpers are useful but not yet a typed review envelope.
- Existing endpoint shape is description-first and app-facing.
- DungeonBuddy needs a draft-oriented producer contract with source refs, terrain/encounter context, markdown, combat defaults, warnings, provenance, and lifecycle state.

This next PR should implement the **first v2 producer API layer** beside the current app API. It should not replace or break the existing generator workflow.

---

## 1. PR goal

Implement a minimal, tested v2 draft contract under the existing StatBlockGenerator router.

Recommended first route set:

```text
GET  /api/statblockgenerator/v2/health
POST /api/statblockgenerator/v2/generate-draft
```

Optional in this PR only if the implementation remains small:

```text
POST /api/statblockgenerator/v2/render-draft
```

Defer unless trivial:

```text
POST /api/statblockgenerator/v2/revise-draft
POST /api/statblockgenerator/v2/parse-draft
```

Reason: the highest-value next step is proving the envelope, models, deterministic default extraction, and route tests. Full revision/parse semantics can come after the draft envelope is real.

---

## 2. Design position

### Keep the existing app API stable

Do not remove, rename, or reshape:

```text
POST /api/statblockgenerator/generate-statblock
```

The v2 API is a producer-facing adapter layer. It should wrap/reuse current generator behavior rather than requiring current clients to migrate.

### Use v2 under the current router

Preferred path for this slice:

```text
/api/statblockgenerator/v2/*
```

This is less disruptive than creating a new `/api/statblocks/*` service boundary. The generic route can be revisited after DungeonBuddy proves consumption.

### Deterministic defaults first

`combat_defaults` should be derived from `StatBlockDetails` wherever possible. Do not ask the LLM to separately invent AC, HP, passive perception, action names, save DCs, or movement summaries if the structured statblock already contains them.

The LLM can generate the statblock. The adapter should compute the combat summary.

### Markdown is a contract field

DungeonBuddy should not need to reconstruct markdown independently just to show the draft. The v2 response should include a stable `markdown` field. The first renderer can be simple and conservative; it does not need final D&D layout polish.

### Accept-to-combat is not persistence

Default `persist` behavior for v2 command-board drafts is `false`. The response should be usable for DungeonBuddy live state, not saved automatically into Firestore, projects, or corpus.

---

## 3. Suggested file shape

Keep the PR reviewable by separating models, adapter helpers, and routes.

Likely files:

```text
statblockgenerator/models/command_board_contract_models.py
statblockgenerator/services/statblock_draft_adapter.py
routers/statblockgenerator_router.py
tests/statblockgenerator/test_command_board_contract_models.py
tests/statblockgenerator/test_statblock_draft_adapter.py
tests/statblockgenerator/test_statblockgenerator_v2_routes.py
Docs/Design/fixtures/statblockgenerator-command-board-contract/*.json
```

Alternative naming is fine, but keep the boundary clear:

- models define the external contract;
- adapter derives request description, markdown, combat defaults, warnings, provenance;
- router handles HTTP only.

---

## 4. Minimum model contract

### Request model

Create a Pydantic model equivalent to the PR #8 fixture envelope.

Core fields:

```python
request_id: str | None
mode: Literal[
    "generate_from_prompt",
    "generate_from_source_statblock",
    "revise_existing",
    "quick_reinforcement",
    "terrain_pressure",
]
intent: DraftIntent
prompt: str | None
source_statblock: dict | StatBlockDetails | None
revision_instructions: list[str]
encounter_context: EncounterContext | None
terrain_context: TerrainContext | None
source_refs: list[SourceRef]
output_options: OutputOptions
```

For this PR, only `generate_from_prompt`, `quick_reinforcement`, and `terrain_pressure` need to be implemented end-to-end. The source/revise modes can validate and return a clear `501` / not-yet-implemented response if necessary, but the models should accept the fixture shapes.

### Response model

Create a stable draft response envelope:

```python
success: bool
draft: StatBlockDraft | None
error: ContractError | None
timestamp: str
```

Draft fields:

```python
draft_id: str
lifecycle_state: Literal["live_draft"]
review_status: Literal["needs_dm_review", "warnings", "failed"]
statblock: StatBlockDetails
markdown: str
combat_defaults: CombatDefaults
warnings: list[ReviewWarning]
provenance: DraftProvenance
```

### Combat defaults

Minimum useful deterministic fields:

```python
name: str
armor_class: int
hit_points: int
initiative_bonus: int | None
passive_perception: int | None
speed_summary: str
primary_actions: list[str]
save_dcs: list[int]
senses_summary: str | None
condition_immunities: str | None
suggested_tactics: list[str]
```

`initiative_bonus` can default to Dexterity modifier. `primary_actions` can be first 2–4 action names. `save_dcs` can be parsed from action/trait descriptions with a simple regex, or left empty if no DC is found.

### Warnings

Start with lightweight warnings, not a perfect legality engine.

Useful first warnings:

- `terrain_assumption`: terrain context exists and generated/action text does not reference any terrain feature.
- `cr_mismatch`: requested target CR differs from returned statblock CR.
- `missing_markdown`: renderer failed or markdown omitted.
- `validation_warning`: mapped from existing `validate_statblock` warnings.

---

## 5. Route behavior

### `GET /api/statblockgenerator/v2/health`

Return one canonical v2 health payload.

Suggested fields:

```json
{
  "status": "ok",
  "service": "statblockgenerator",
  "contract": "command_board_draft_v2",
  "version": "0.1.0",
  "generator_ready": true,
  "openai_configured": true,
  "supports": ["generate-draft"],
  "timestamp": "..."
}
```

Note: PR #8 called out duplicate `/health` definitions on the current router. This PR can leave legacy `/health` alone if necessary, but v2 health must be canonical and unambiguous.

### `POST /api/statblockgenerator/v2/generate-draft`

Behavior:

1. Validate the v2 request model.
2. Convert v2 request into a current `CreatureGenerationRequest`.
3. Call `StatBlockGenerator.generate_creature()`.
4. Validate or lightly review the returned `StatBlockDetails`.
5. Render markdown.
6. Derive combat defaults deterministically.
7. Build warnings.
8. Return the v2 draft envelope.

The conversion from v2 request to existing description should be transparent and testable. Example description composition:

```text
Intent: <intent.summary>
Target CR: <intent.target_cr>
Role: <intent.target_role>
Tone: <intent.tone>
Prompt: <prompt>
Encounter context: ...
Terrain context: ...
Constraints: ...
Revision instructions: ...
```

This does not need to be the final prompt architecture; it is an adapter layer to prove the API.

---

## 6. Test expectations

### Contract model tests

Use all five fixtures from:

```text
Docs/Design/fixtures/statblockgenerator-command-board-contract/
```

Assert:

- each fixture validates as the v2 request model;
- default `persist` is false if omitted;
- unsupported/invalid mode fails clearly;
- empty or missing prompt is only allowed when source/revision context is sufficient.

### Adapter tests

Use a sample `StatBlockDetails` and assert deterministic outputs:

- markdown contains name, AC, HP, speed, CR, actions;
- combat defaults include name, AC, HP, initiative bonus, passive perception, speed summary, action names;
- CR mismatch warning fires when requested CR differs from generated CR;
- terrain assumption warning can fire when terrain exists but output ignores terrain.

### Route tests

Mock `StatBlockGenerator.generate_creature()`; do not call OpenAI.

Assert:

- `GET /api/statblockgenerator/v2/health` returns the v2 contract payload;
- `POST /api/statblockgenerator/v2/generate-draft` accepts at least `generate_from_prompt.basic.json`;
- response includes `draft.lifecycle_state == "live_draft"`;
- response includes `markdown`, `combat_defaults`, `warnings`, `provenance`;
- generation failure maps to a stable error envelope.

Do not require live OpenAI tests for this PR.

---

## 7. Out of scope

Do not build DungeonBuddy client code.

Do not add corpus promotion or DungeonBuddy safe-write integration.

Do not add Firestore persistence for v2 drafts.

Do not rewrite the full StatBlockGenerator frontend workflow.

Do not remove current app endpoints.

Do not implement the final balance/legality engine.

Do not build image generation, 3D model generation, or export PDF integration into this v2 draft route.

---

## 8. Acceptance criteria

The next PR is ready when:

- v2 request/response Pydantic models exist;
- all five PR #8 fixture JSON files validate against the request model, or the PR clearly documents why one fixture is deferred;
- `GET /api/statblockgenerator/v2/health` works;
- `POST /api/statblockgenerator/v2/generate-draft` works with mocked generation;
- the response envelope includes structured statblock, markdown, combat defaults, warnings, provenance, and lifecycle state;
- existing `/api/statblockgenerator/generate-statblock` behavior remains unchanged;
- unit/route tests cover success and failure paths;
- no live OpenAI call is required in CI.

---

## 9. Suggested PR description

```markdown
### Motivation

This PR implements the first StatBlockGenerator v2 producer contract needed by DungeonBuddy command-board integration. PR #8 captured the audit and fixture baseline; this PR turns that baseline into Pydantic models, deterministic draft adaptation, v2 health, and a mocked generate-draft route.

### Description

- Added v2 command-board request/response models for statblock drafts.
- Added a draft adapter that converts command-board requests into the existing generator core, renders markdown, derives combat defaults, adds lightweight warnings, and records provenance.
- Added `GET /api/statblockgenerator/v2/health`.
- Added `POST /api/statblockgenerator/v2/generate-draft` without changing existing `/generate-statblock` behavior.
- Added contract/model/adapter/route tests using the PR #8 fixture pack with mocked generation.

### Testing

- `uv run python -m pytest tests/statblockgenerator/test_command_board_contract_models.py -v`
- `uv run python -m pytest tests/statblockgenerator/test_statblock_draft_adapter.py -v`
- `uv run python -m pytest tests/statblockgenerator/test_statblockgenerator_v2_routes.py -v`
```

---

## 10. Design note for the agent

The point of this PR is **not** to make the generator perfect. The point is to create a reliable seam for DungeonBuddy.

A slightly plain draft with stable markdown/defaults/provenance is better than a clever endpoint with hidden behavior. Keep the route boring, typed, mocked in tests, and safe to call from another product.
