# HANDOFF — PR13 Statblock v1 contract models and fixtures

**Status:** READY AFTER PR12  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessor:** PR12 bounded-context foundation  
**Successor:** `HANDOFF-pr14-statblock-v1-canonicalization-validation-digest.md`  
**Authority:** `Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md`

## 0. Mission

Translate the approved contract design into executable Pydantic models and representative fixtures without adding provider, persistence, or production write behavior.

The output of this PR becomes the one canonical mechanics language used later for Structured Outputs, API editing, validation, and revision storage.

## 1. Contract boundary

Implement at minimum:

```text
StatblockDefinitionV1
RulesetRef
CreatureIdentity
DefenseProfile
VitalityProfile
MovementProfile
AbilityScores
ProficiencyProfile
SenseProfile
CommunicationProfile
ChallengeProfile
ResourcePool
RuleElement
CreaturePhase
LairProfile
StatblockFlavorText
```

Implement the typed primitives and discriminated unions required by the design:

```text
DiceExpression
Distance
Activation
Trigger
Usage
Duration
Targeting
ResourceCost
AttackMechanic
SaveEffectMechanic
MultiattackMechanic
MovementMechanic
SpellcastingMechanic
UtilityMechanic
HumanAdjudicatedMechanic
Effect union
```

## 2. Editorial constraints

### 2.1 Section is not mechanic kind

Preserve three independent axes:

```text
section
activation
mechanic.kind
```

Do not reintroduce separate top-level classes such as `ReactionElement` or `LegendaryActionElement` merely because an element appears in that section.

### 2.2 Definition-local keys

Require readable definition-local keys for:

- rule elements;
- movement profiles where referenced;
- resource pools;
- phases;
- damage interactions and armor profiles when addressable.

Keys must be unique in their namespace and use a constrained format. Do not generate global UUIDs inside the definition.

### 2.3 Typed flexibility

Include an explicit `human_adjudicated` mechanic. Do not add an arbitrary `extensions: dict` or open-ended `Any` escape hatch to canonical mechanics.

### 2.4 One naming convention

Use one canonical JSON naming convention for v1. Do not enable old camelCase/snake_case dual population for compatibility.

### 2.5 No server facts

`StatblockDefinitionV1` must not contain:

- candidate/statblock/revision IDs;
- timestamps;
- content digest;
- project/session IDs;
- DungeonBuddy graph IDs;
- review status;
- persistence location;
- CSS or Markdown;
- mutable combat state.

## 3. Structured Outputs compatibility

Produce two schema artifacts from the same model source:

```text
canonical JSON Schema/OpenAPI representation
OpenAI strict-compatible schema representation
```

The OpenAI representation may transform schema syntax but must preserve semantic fields, nesting, enums, and discriminators.

No OpenAI request is made in this PR.

Add snapshot or golden-file tests that make contract changes reviewable.

## 4. Required fixtures

Create complete valid JSON fixtures under a versioned fixture directory.

### Valid fixtures

1. **Simple bruiser** — attacks, damage, ordinary movement, no advanced resources.
2. **Spellcaster** — innate or slot casting with typed groups.
3. **Legendary creature** — named legendary resource pool and action costs.
4. **Lair creature** — lair profile and lair-section elements.
5. **Unusual movement** — burrow/hover/special qualifier plus activated movement.
6. **Mythic phase** — explicit phase entry trigger and enabled elements.
7. **Human-adjudicated mechanic** — complete rules text and manual automation support.

### Invalid fixtures

1. duplicate rule-element key;
2. dangling multiattack element reference;
3. phase references unknown element;
4. resource cost references unknown pool;
5. section/activation contradiction;
6. formula HP missing formula;
7. more than one default armor class;
8. unknown ruleset value.

Structural invalidity may fail Pydantic immediately. Cross-reference invalidity may be reserved for PR14, but the fixtures must exist now and be clearly classified.

## 5. Field-disposition artifact

Add a checked table mapping every current `StatBlockDetails` field to one of:

```text
retained directly
retained but restructured
derived by server
moved to candidate envelope
moved to revision envelope
moved to DungeonBuddy
removed
```

This table should live beside the contract models or in `Docs/Design` and cite the exact new field.

## 6. Suggested package shape

```text
statblocks_v1/domain/models.py
statblocks_v1/domain/primitives.py
statblocks_v1/domain/rule_elements.py
statblocks_v1/domain/schema.py
Docs/Design/fixtures/dungeonbuddy-statblock-v1/*.json
tests/statblocks_v1/test_models.py
tests/statblocks_v1/test_schema_snapshots.py
tests/statblocks_v1/test_fixtures.py
```

Split files further when it improves readability; do not create one new 1,000-line model file.

## 7. Testing requirements

Required tests:

- every valid fixture parses;
- parsed fixture round-trips to canonical JSON without information loss;
- structural invalid fixtures fail with stable error locations;
- discriminators select the intended mechanic/effect subtype;
- no canonical model permits unknown fields silently;
- schema artifacts are deterministic;
- OpenAI schema contains no unsupported constructs known to the compiler;
- domain tests run without FastAPI app, OpenAI, Firebase, or Cloudflare imports.

## 8. Acceptance criteria

PR13 is complete when:

- the full v1 definition can represent every required fixture;
- the model is directly usable as a Structured Outputs response model in principle;
- the field-disposition table covers all legacy fields;
- there is no arbitrary compatibility bag;
- fixtures expose advanced mechanics rather than only simple attacks;
- schema changes produce visible snapshot diffs;
- all focused tests run successfully.

## 9. Non-goals

- no semantic balance judgment;
- no digest calculation;
- no OpenAI call;
- no Firestore;
- no FastAPI generation endpoint;
- no DungeonBuddy TypeScript generation yet;
- no legacy payload adapter.

## 10. Successor handoff

Before merge, update PR14’s handoff with:

- exact model and discriminator names;
- schema artifact paths;
- fixture directory;
- fields that require cross-field validation;
- places where the implementation intentionally diverged from illustrative names in the design document.
