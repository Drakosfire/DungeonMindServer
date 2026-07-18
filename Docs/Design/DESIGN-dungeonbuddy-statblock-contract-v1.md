# Design: DungeonBuddy Statblock Contract v1

**Status:** ACTIVE DESIGN DIRECTION  
**Created:** 2026-07-17  
**Owner:** DungeonMindServer  
**Consumer:** DungeonMindBuddy  
**Contract name:** `dungeonmind.dungeonbuddy-statblocks`  
**Contract version:** `1.0.0`  
**Repository anchor reviewed:** `b3cae86b9e0dbc55fc26412be19f9e0445c9b9d7`

## 1. Decision summary

DungeonMindServer owns the canonical statblock contract consumed by DungeonBuddy.
DungeonBuddy is a first-party extension of DungeonMind, not an independent authority that
copies or reinterprets the statblock schema.

This contract is a clean design. It does **not** preserve wire compatibility with:

- `StatBlockDetails`;
- `/api/statblockgenerator/generate-statblock`;
- `/api/statblockgenerator/v2/generate-draft`;
- the current StatBlockGenerator project/session document shape;
- current camelCase/snake_case dual-input behavior;
- Markdown-first draft envelopes;
- mutable project documents as the durable statblock identity.

The existing generator, prompt manager, Structured Outputs machinery, internal service
authentication, validation code, Firestore access, Cloudflare image pipeline, renderers,
and fixtures are predecessor evidence and reusable implementation. They are not contract
constraints.

The central architecture is:

```text
DungeonBuddy authors a ThreatDraft
→ DungeonMindServer generates a StatblockDefinitionV1 through Structured Outputs
→ DungeonMindServer validates and wraps it as a GeneratedStatblockCandidateV1
→ DungeonBuddy projects, edits, regenerates, accepts, or rejects
→ DungeonBuddy submits the complete accepted definition
→ DungeonMindServer validates, canonicalizes, digests, and persists an immutable revision
→ DungeonBuddy binds its Threat node to the exact persisted revision
```

## 2. Scrutinizing editorial resolutions

Several earlier ideas were directionally correct but needed sharper boundaries.

### 2.1 The contract owner is DungeonMindServer

DungeonMindServer owns:

- the Pydantic domain models;
- canonical JSON Schema and OpenAPI publication;
- the OpenAI Structured Outputs schema compiler;
- generation requests and candidate responses;
- validation semantics;
- logical statblock and immutable revision identity;
- canonicalization and digests;
- revision persistence;
- CDN asset references returned by its image pipeline.

DungeonBuddy owns:

- ThreatDraft and Threat identity;
- graph authorship and relationships;
- human review and acceptance decisions;
- visual projections and design system styling;
- Plan, scene, and Play placement;
- campaign-specific preferred revision selection;
- combat runtime state.

DungeonBuddy may create mechanical revisions, but it does so by submitting a complete
`StatblockDefinitionV1` to DungeonMindServer. It does not fork or own the mechanics schema.

### 2.2 The OpenAI response is the canonical definition shape

The model should generate the same semantic `StatblockDefinitionV1` used by:

1. DungeonMindServer generation;
2. DungeonBuddy mechanical editing;
3. DungeonMindServer validation;
4. immutable revision persistence;
5. DungeonBuddy rendering and combat-seed derivation.

The model does **not** generate server facts such as candidate IDs, statblock IDs, revision
IDs, digests, timestamps, persistence locators, validation receipts, or review decisions.
DungeonMindServer constructs those envelopes.

### 2.3 One definition, not several drifting representations

The canonical mechanics object is the structured definition. Markdown, summary cards,
combat defaults, embeddings, and full statblock views are derived projections.

The API must not make Markdown or a copied `combat_defaults` object co-authoritative with
the definition.

### 2.4 Presentation section and mechanic kind are different axes

The earlier idea of separate `ReactionElement`, `LegendaryActionElement`, and
`LairActionElement` classes conflated where an element appears with what it mechanically
does.

The refined design separates:

```text
section
  where the element is presented and which action-economy lane it occupies

activation
  how and when it is invoked

mechanic.kind
  what mechanical structure it contains
```

A reaction may use an attack mechanic. A legendary action may use an attack, save, movement,
or human-adjudicated mechanic. A trait may be passive or triggered. This orthogonal shape is
more expressive with fewer artificial subtypes.

### 2.5 Typed flexibility does not mean a complete rules engine

The contract should structure the mechanics DungeonBuddy must reliably edit, summarize,
link, and use in combat. It should not attempt to encode all possible 5e prose as executable
logic.

A known `human_adjudicated` mechanic remains a first-class typed case. Both services know to
preserve, render, edit, search, and expose it while declining to claim deterministic
automation.

### 2.6 Rules text is part of the one canonical definition

Each rule element may contain both typed semantics and human-facing `rules_text`. These are
not separate documents or owners; together they form one accepted definition.

For structured mechanics, typed fields are authoritative for machine interaction and
`rules_text` is the complete table-facing expression. DungeonMindServer validates material
contradictions before revision persistence. For a `human_adjudicated` mechanic,
`rules_text` is the mechanic.

Clients must not silently regenerate or overwrite rules text from typed fields. Editing
either side requires revalidation.

## 3. Scope and non-goals

This design defines:

- the new statblock domain model;
- the field-by-field replacement of `StatBlockDetails`;
- typed rule elements and shared primitives;
- Structured Outputs use;
- candidate and revision envelopes;
- dedicated DungeonBuddy-facing internal routes;
- identity, canonicalization, validation, and persistence rules;
- image and asset references;
- renderer and combat-consumer obligations;
- fixtures and acceptance criteria.

This design does not:

- migrate existing project documents;
- preserve old route behavior;
- define DungeonBuddy Threat graph storage;
- define final UI layout or CSS;
- automate every 5e mechanic;
- make the browser a privileged DungeonMindServer client;
- make display names identity;
- allow arbitrary extension dictionaries;
- make latest revision automatically replace a pinned campaign reference.

## 4. Resource model

### 4.1 `StatblockDefinitionV1`

The canonical reusable mechanics object. It has no server identity or lifecycle metadata.

```text
StatblockDefinitionV1
  ruleset
  identity
  defenses
  vitality
  movement
  abilities
  proficiencies
  senses
  communication
  challenge
  resources
  rule_elements
  phases
  lair
  flavor_text
```

### 4.2 `GeneratedStatblockCandidateV1`

A server-produced proposal awaiting DungeonBuddy judgment.

```text
GeneratedStatblockCandidateV1
  candidate_id
  contract
  contract_version
  definition
  validation_receipt
  generation_receipt
  asset_brief
  assets
```

A candidate is not accepted mechanics truth. It may be edited, regenerated, rejected, or
allowed to expire.

### 4.3 `StatblockResourceV1`

The stable logical identity for a reusable statblock design.

```text
StatblockResourceV1
  statblock_id
  latest_revision_id
  created_at
  created_by
```

`latest_revision_id` is chronological server metadata. It is not a campaign preference.
DungeonBuddy chooses which revision a Threat or placement uses.

### 4.4 `StatblockRevisionResourceV1`

One immutable accepted revision.

```text
StatblockRevisionResourceV1
  statblock_id
  revision_id
  parent_revision_id
  contract
  contract_version
  definition
  definition_digest
  validation_receipt
  provenance
  asset_bindings
  created_at
```

Accepted revisions are append-only and never overwritten.

## 5. Canonical definition

A representative shape follows. Exact Pydantic naming may change during implementation,
but the ownership and semantics are locked by this document.

```python
class StatblockDefinitionV1(BaseModel):
    ruleset: RulesetRef
    identity: CreatureIdentity
    defenses: DefenseProfile
    vitality: VitalityProfile
    movement: MovementProfile
    abilities: AbilityScores
    proficiencies: ProficiencyProfile
    senses: SenseProfile
    communication: CommunicationProfile
    challenge: ChallengeProfile
    resources: list[ResourcePool] = []
    rule_elements: list[RuleElement]
    phases: list[CreaturePhase] = []
    lair: LairProfile | None = None
    flavor_text: StatblockFlavorText | None = None
```

### 5.1 Ruleset

```text
RulesetRef
  system: dnd5e
  edition: 2014 | 2024
  house_ruleset_id: optional opaque identifier
```

The generation request declares the target ruleset. The definition repeats it so exports and
stored revisions are self-describing. The Structured Outputs schema constrains it to the
requested value.

### 5.2 Identity

```text
CreatureIdentity
  name
  size
  creature_type
  subtypes[]
  alignment: optional
```

Display names are not logical identity. Renaming does not merge or split a statblock unless
the caller explicitly creates a different logical resource.

### 5.3 Defenses

```text
DefenseProfile
  armor_classes[]
  damage_interactions[]
  condition_immunities[]
```

An armor class is a typed profile rather than one integer:

```text
ArmorClassProfile
  key
  value
  label: optional
  condition: optional rules text
  default: boolean
```

Damage interactions are typed:

```text
DamageInteraction
  key
  kind: vulnerability | resistance | immunity
  damage_types[]
  qualifiers[]
  bypasses[]
```

This can represent, for example, resistance to nonmagical bludgeoning, piercing, and
slashing damage except from silvered weapons without flattening the mechanic into one string.

### 5.4 Vitality

```text
VitalityProfile
  hit_points
```

```text
HitPointProfile
  method: formula | fixed
  formula: optional DiceExpression
  fixed_value: optional integer
  displayed_average: optional explicit override
```

DungeonMindServer derives the normal average from a formula and verifies any displayed
average. Fixed HP remains supported for entities that do not use hit dice.

### 5.5 Movement

Movement becomes a list instead of fixed optional object properties:

```text
MovementProfile
  modes[]
```

```text
MovementMode
  key
  mode: walk | fly | swim | climb | burrow | hover | special
  distance
  unit: feet
  qualifiers[]
```

Teleportation, phase movement, and other activated movement should normally be rule elements,
not ordinary speed modes.

### 5.6 Abilities and proficiencies

Ability scores remain a typed six-score object.

```text
AbilityScores
  strength
  dexterity
  constitution
  intelligence
  wisdom
  charisma
```

Ability modifiers are derived and are not independently authored.

```text
ProficiencyProfile
  proficiency_bonus
  saving_throws[]
  skills[]
```

```text
SavingThrowBonus
  ability
  value
  derivation: standard | expertise | explicit_override
  note: optional

SkillBonus
  skill
  value
  derivation: standard | expertise | explicit_override
  note: optional
```

DungeonMindServer verifies standard derivations and preserves intentional overrides.

### 5.7 Senses and communication

```text
SenseProfile
  senses[]
  passive_perception

Sense
  kind: darkvision | blindsight | tremorsense | truesight | special
  range
  unit: feet
  qualifiers[]
```

```text
CommunicationProfile
  languages[]
  telepathy_range: optional
  special_modes[]
```

Languages are a list, not comma-delimited prose.

### 5.8 Challenge

```text
ChallengeProfile
  rating
  proficiency_bonus
  xp_override: optional
```

The rating uses a canonical string, including fractions. XP is derived from the selected
ruleset unless explicitly overridden.

### 5.9 Resources

Named resource pools support legendary action budgets, charges, and other shared mechanics.

```text
ResourcePool
  key
  name
  maximum
  refresh
  rules_text: optional
```

Spell slots may remain inside a spellcasting mechanic when they are intrinsic to that feature.
A shared resource should use a resource pool when several rule elements spend or restore it.

### 5.10 Flavor text

```text
StatblockFlavorText
  summary: optional
  description: optional
```

This is reusable mechanics-adjacent presentation text. It is not the DungeonBuddy Threat's
campaign-specific identity, history, or graph description.

## 6. Rule element model

### 6.1 Common shape

```python
class RuleElement(BaseModel):
    key: str
    name: str
    section: RuleSection
    summary: str | None
    rules_text: str
    activation: Activation
    usage: Usage
    costs: list[ResourceCost]
    mechanic: Mechanic
    tags: list[str]
    automation_support: AutomationSupport
```

`key` is definition-local identity. It must be unique inside the definition and remain stable
across revisions when the same conceptual element is retained, even if its name changes.

A persisted rule element can be addressed by:

```text
statblock_id + revision_id + element_key
```

The model generates readable semantic keys such as `hooked_limb` or `geometry_break`; it does
not generate global UUIDs.

### 6.2 Sections

```text
trait
action
bonus_action
reaction
legendary_action
lair_action
regional_effect
```

Section controls presentation and expected action-economy validation. It does not determine
the mechanic subtype.

### 6.3 Activation

```text
Activation
  kind: passive | action | bonus_action | reaction | triggered | legendary | lair_initiative | special
  trigger: optional Trigger
  timing_text: optional
```

### 6.4 Usage

```text
Usage
  kind: at_will | recharge | per_turn | per_round | per_day | once | resource | spell_slots | manual
  recharge_range: optional
  uses: optional
  resource_key: optional
  refresh_text: optional
```

`spell_slots` marks slot-backed prepared/known spell groups. Slot count lives on
`SpellGroup.slots`; do not overload `at_will` for limited slot casting.

### 6.5 Costs

```text
ResourceCost
  resource_key
  amount
```

Legendary action costs are represented through the same mechanism rather than special fields
inside an otherwise shallow action.

### 6.6 Mechanic union

The first contract supports a finite discriminated union:

```text
Mechanic =
  AttackMechanic
  SaveEffectMechanic
  MultiattackMechanic
  SpellcastingMechanic
  PassiveMechanic
  CompositeMechanic
  PhaseTransitionMechanic
  HumanAdjudicatedMechanic
```

This list can gain new variants in a future major or compatible minor contract revision. It
must not be replaced by `Dict[str, Any]` or an arbitrary `extensions` bag.

### 6.7 Attack mechanic

```text
AttackMechanic
  kind: attack
  attack_type: melee_weapon | ranged_weapon | melee_spell | ranged_spell | special
  attack_bonus
  reach: optional Distance
  range: optional RangeProfile
  target
  hit_effects[]
  miss_effects[]
```

### 6.8 Save-effect mechanic

```text
SaveEffectMechanic
  kind: save_effect
  save
  target
  failure_effects[]
  success_effects[]
```

```text
SavingThrow
  ability
  dc
```

### 6.9 Multiattack mechanic

```text
MultiattackMechanic
  kind: multiattack
  sequences[]

ElementUse
  element_key
  count
  choice_group: optional
```

Every referenced key must exist and be legal for the sequence.

### 6.10 Spellcasting mechanic

Spellcasting is a rule element and may occur more than once.

```text
SpellcastingMechanic
  kind: spellcasting
  casting_mode: prepared | known | innate | charges | special
  ability: optional
  save_dc: optional
  attack_bonus: optional
  caster_level: optional
  groups[]
```

```text
SpellGroup
  usage
  level: optional
  slots: optional
  spells[]

SpellRef
  name
  school: optional
  source_id: optional
  rules_text: optional
```

Spell level is authored only on `SpellGroup.level`, never on `SpellRef`, so a
group cannot contradict its members.

This supports normal slots, innate at-will spells, per-day spells, and charge-based casting
without forcing all casters into one block.

### 6.11 Passive and composite mechanics

```text
PassiveMechanic
  kind: passive
  effects[]

CompositeMechanic
  kind: composite
  target: optional
  effects[]
```

### 6.12 Phase transition mechanic

```text
PhaseTransitionMechanic
  kind: phase_transition
  destination_phase_key
  effects[]
```

The trigger belongs to activation. Effects may restore HP, reset resources, enable or disable
elements, or otherwise alter phase state.

### 6.13 Human-adjudicated mechanic

```text
HumanAdjudicatedMechanic
  kind: human_adjudicated
  adjudication_tags[]
```

Its mechanical truth is `rules_text`. `automation_support` must be `manual`.

## 7. Shared effect primitives

The initial effect union is deliberately useful but bounded:

```text
Effect =
  DamageEffect
  HealingEffect
  ConditionEffect
  MovementEffect
  ForcedMovementEffect
  ResourceChangeEffect
  SummonEffect
  StatModifierEffect
  EnableElementsEffect
  DisableElementsEffect
  EnterPhaseEffect
  HumanAdjudicatedEffect
```

Common supporting primitives include:

```text
DiceExpression
  count
  die
  modifier

Distance
  value
  unit: feet

RangeProfile
  normal
  long: optional

TargetProfile
  kind: creature | creatures | self | point | area | object | structure | special
  count: optional
  range: optional
  area: optional
  qualifiers[]

Duration
  kind: instantaneous | until_start_turn | until_end_turn | rounds | minutes | hours | until_save | permanent | special
  value: optional

Trigger
  kind
  source_element_key: optional
  condition_text: optional
```

Effect arrays are flat. The first version does not introduce recursive programs or arbitrary
condition trees.

## 8. Phases, legendary economy, and lairs

### 8.1 Creature phases

```text
CreaturePhase
  key
  name
  default
  enabled_element_keys[]
  disabled_element_keys[]
  entry_rules_text: optional
```

Use internal phases when the creature changes state during one encounter and the transition
is part of one continuous statblock.

Use separate logical statblocks when forms are independently reusable, selectable, placed, or
prepared.

### 8.2 Legendary actions

Legendary action economy is represented by:

- a named resource pool, normally `legendary_actions`;
- refresh timing on that pool;
- rule elements in the `legendary_action` section;
- resource costs on each option.

This avoids a special container whose children revert to the old shallow `Action` shape.

### 8.3 Lairs

```text
LairProfile
  name: optional
  description: optional
  initiative_count: optional
  initiative_tiebreak: optional
  regional_rules_text: optional
```

Individual lair actions remain ordinary typed rule elements in the `lair_action` section.

## 9. Field-by-field replacement of `StatBlockDetails`

| Current field | Contract v1 disposition |
|---|---|
| `name` | `identity.name` |
| `size` | `identity.size` |
| `type` | `identity.creature_type` |
| `subtype` | `identity.subtypes[]` |
| `alignment` | `identity.alignment`, optional |
| `armor_class: int` | `defenses.armor_classes[]` with one default profile |
| `hit_points: int` | derived/displayed through `vitality.hit_points` |
| `hit_dice: str` | typed `DiceExpression` when formula-based |
| fixed `speed` object | `movement.modes[]` |
| `abilities` | retained with unambiguous full ability names |
| `saving_throws: Dict[str, int]` | `proficiencies.saving_throws[]` |
| `skills: Dict[str, int]` | `proficiencies.skills[]` |
| `damage_resistance: str` | typed `DamageInteraction[]` |
| `damage_immunity: str` | typed `DamageInteraction[]` |
| `damage_vulnerability: str` | typed `DamageInteraction[]` |
| `condition_immunity: str` | `defenses.condition_immunities[]` |
| fixed `senses` object | typed `senses.senses[]` plus passive Perception |
| `languages: str` | `communication.languages[]` and special modes |
| `challenge_rating: str | float` | canonical string `challenge.rating` |
| `xp` | ruleset-derived, with optional explicit override |
| `proficiency_bonus` | `challenge.proficiency_bonus`, validated against ruleset |
| `actions` | rule elements with `section: action` |
| `bonus_actions` | rule elements with `section: bonus_action` |
| `reactions` | rule elements with `section: reaction` |
| `special_abilities` | rule elements with `section: trait` |
| `spells` | one or more `SpellcastingMechanic` rule elements |
| `legendary_actions.actions_per_turn` | named resource pool maximum |
| `legendary_actions.actions` | typed rule elements with resource costs |
| `lair_actions.initiative` | `lair.initiative_count` |
| `lair_actions.actions` | typed rule elements with `section: lair_action` |
| `description` | split into reusable `flavor_text` and DungeonBuddy Threat description |
| `sd_prompt` | candidate `asset_brief`; excluded from mechanics definition |
| `project_id` | removed from definition |
| `created_at` | server candidate or revision envelope |
| `last_modified` | removed; revisions are immutable |
| `tags` | logical statblock metadata or DungeonBuddy Threat metadata, not mechanics |

### 9.1 Replacement of current `Action`

| Current `Action` field | Contract v1 disposition |
|---|---|
| `name` | `RuleElement.name` |
| `desc` | `RuleElement.rules_text` |
| `attack_bonus` | `AttackMechanic.attack_bonus` when applicable |
| `damage` string | typed `DamageEffect` with `DiceExpression` |
| `damage_type` | `DamageEffect.damage_type` |
| `range` string | typed reach/range/target profiles |
| `recharge` string | typed `Usage` |

### 9.2 Replacement of current spell model

| Current field | Contract v1 disposition |
|---|---|
| one `SpellcastingBlock` | multiple spellcasting rule elements allowed |
| `level` | `caster_level`, optional according to casting mode |
| `ability` | typed ability enum |
| `save_dc` | retained in casting profile |
| `attack_bonus` | retained in casting profile |
| `cantrips` / `known_spells` | `SpellGroup[]` |
| fixed level 1–9 slot fields | slot-bearing groups or typed slot mapping |
| inline spell description | optional `SpellRef.rules_text`; canonical spell locator preferred later |

## 10. Generation request and candidate response

### 10.1 Generate request

```json
{
  "request_id": "req_...",
  "ruleset": {
    "system": "dnd5e",
    "edition": "2024"
  },
  "source": {
    "name_hint": "Tripod Null-Calf",
    "description": "A three-legged siege scout that tests defensive geometry...",
    "description_digest": "sha256:..."
  },
  "intent": {
    "target_cr": "5",
    "roles": ["controller", "siege"],
    "complexity": "standard",
    "must_include": ["pins gates and rope lines"],
    "must_avoid": ["flight"]
  },
  "context": {
    "party_level": 5,
    "party_size": 6,
    "terrain_notes": ["narrow gate throat", "civilian cure line"]
  },
  "asset_options": {
    "include_generation_brief": true,
    "generate_images": false
  }
}
```

The request carries an authored description snapshot and generation intent, not the complete
DungeonBuddy Threat object.

### 10.2 Revise request

A revision request includes:

```text
request_id
ruleset
source_definition or exact source revision locator
revision_instructions[]
optional updated authored description snapshot
optional encounter context
asset options
```

The response is another candidate, not a persisted revision.

### 10.3 Candidate response

```json
{
  "contract": "dungeonmind.dungeonbuddy-statblocks",
  "contract_version": "1.0.0",
  "candidate_id": "candidate_...",
  "definition": {},
  "validation_receipt": {
    "status": "warnings",
    "issues": []
  },
  "generation_receipt": {
    "request_id": "req_...",
    "generator_version": "...",
    "model": "...",
    "prompt_version": "...",
    "created_at": "..."
  },
  "asset_brief": {
    "prompt": "...",
    "recommended_roles": ["portrait", "token"]
  },
  "assets": []
}
```

There is no canonical Markdown, combat-default copy, DungeonBuddy review status, or graph
lifecycle in this response.

## 11. Persistence requests

### 11.1 Create logical statblock and first revision

```text
POST /api/internal/dungeonbuddy/v1/statblocks
```

The request includes:

```text
idempotency_key
candidate_id: optional provenance
complete definition
change_summary
accepted_through
asset_bindings[]
```

DungeonMindServer validates, canonicalizes, digests, creates `statblock_id` and
`revision_id`, persists the immutable revision, and returns the exact persisted resource.

### 11.2 Append revision

```text
POST /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
```

The request additionally includes `parent_revision_id`. The server rejects an unknown parent
or an optimistic-concurrency conflict rather than silently rebasing.

## 12. Internal route family

The new router is dedicated to the DungeonBuddy contract:

```text
POST /api/internal/dungeonbuddy/v1/statblock-candidates:generate
POST /api/internal/dungeonbuddy/v1/statblock-candidates:revise
POST /api/internal/dungeonbuddy/v1/statblock-definitions:validate

POST /api/internal/dungeonbuddy/v1/statblocks
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
POST /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions
GET  /api/internal/dungeonbuddy/v1/statblocks/{statblock_id}/revisions/{revision_id}
```

A future candidate read route may be added if candidates are durably retained. Acceptance
must send the complete definition so candidate expiry never blocks persistence.

The browser never calls these routes directly. DungeonBuddy backend uses the existing internal
service-authentication pattern or its deliberate successor.

## 13. Structured Outputs architecture

The authoritative chain is:

```text
Pydantic StatblockDefinitionV1
→ canonical JSON Schema and OpenAPI
→ strict-schema compiler for OpenAI Structured Outputs
→ generated DungeonBuddy TypeScript DTO/client
```

The strict-schema compiler may rewrite JSON Schema syntax required by the provider, but it may
not produce a semantically different payload.

The model returns only `StatblockDefinitionV1`.

DungeonMindServer owns the outer generation outcome:

```text
GenerationOutcome =
  succeeded
  refused
  incomplete
  provider_failed
  definition_invalid
```

Only `succeeded` contains a candidate definition.

The definition schema should avoid:

- arbitrary dictionaries;
- unbounded recursion;
- model-generated global IDs;
- unsupported schema keywords leaking into the provider call;
- redundant derived fields that the server cannot validate;
- extremely deep unions created only for theoretical completeness.

## 14. Validation

Validation occurs in layers:

```text
1. schema validation
2. definition-local key uniqueness
3. internal reference validation
4. ruleset validation
5. deterministic arithmetic and derivation checks
6. action-economy and section/activation consistency
7. typed-semantics versus rules-text coherence
8. revision lineage and persistence invariants
```

Validation issues have:

```text
code
severity: info | warning | error
field_path
message
suggested_resolution: optional
```

Errors block revision persistence. Warnings may be accepted by DungeonBuddy and are preserved
in the revision validation receipt.

## 15. Canonicalization and digest

Before persistence DungeonMindServer:

1. validates the definition;
2. normalizes enums, keys, dice, and optional fields according to the contract;
3. preserves semantically meaningful array order, especially rule-element display order;
4. canonicalizes JSON using RFC 8785 JSON Canonicalization Scheme;
5. computes SHA-256 over the canonical definition;
6. persists the canonical definition and digest together.

The digest covers the mechanics definition. It does not change when a DungeonBuddy Threat
changes its graph description or preferred image.

Asset bindings and server provenance are outside the definition digest and may have their own
integrity metadata.

## 16. Identity and idempotency

```text
candidate_id
  one generated or edited proposal envelope

statblock_id
  stable logical mechanics identity

revision_id
  one immutable accepted revision

element_key
  stable definition-local identity for one rule element
```

Required behavior:

```text
same idempotency key + same payload
  → same persisted outcome

same idempotency key + different payload
  → conflict error

changed accepted mechanics
  → same statblock_id, new revision_id

same display name
  → no identity merge

unchanged element across revisions
  → preserve element_key
```

## 17. Error envelope

```json
{
  "success": false,
  "error": {
    "code": "definition_invalid",
    "message": "The proposed statblock definition failed validation.",
    "request_id": "req_...",
    "issues": []
  }
}
```

Initial stable codes:

```text
invalid_request
generation_refused
generation_incomplete
generation_failed
definition_invalid
candidate_not_found
statblock_not_found
revision_not_found
revision_conflict
idempotency_conflict
unauthorized_internal_client
internal_error
```

No route returns partial success while implying that persistence or revision creation
completed.

## 18. Images and assets

Images remain CDN-backed references.

```text
AssetRef
  asset_id
  url
  role
  mime_type
  alt_text
  width: optional
  height: optional
  prompt: optional
  provenance
```

Candidate generation may return an asset brief and generated assets. Assets are not part of
the mechanics definition.

DungeonBuddy normally owns the preferred identity image on the Threat. A persisted statblock
revision may carry reusable asset bindings for a specific form, phase, token, or sheet image.
Changing campaign image selection does not create a mechanics revision.

## 19. DungeonBuddy consumer contract

DungeonBuddy must:

- consume generated types or a generated client from DungeonMindServer's OpenAPI;
- avoid hand-maintained duplicate transport interfaces;
- retain exact `statblock_id` and `revision_id` locators;
- pin Plan, scene, prepared encounter, export, and combat references to exact revisions;
- derive summaries and combat seeds from the definition rather than copied API fields;
- submit a complete definition for every accepted initial revision or later mechanical edit;
- preserve element keys for unchanged mechanics;
- display human-adjudicated mechanics without claiming automation;
- keep current HP, initiative, conditions, and encounter-local changes outside the revision.

The first combat adapter derives at least:

```text
name
default armor class
maximum hit points
initiative modifier
speed summary
exact statblock revision locator
```

The existing tracker may be upgraded before it is rebuilt as a Play surface.

## 20. Rendering obligations

The dedicated statblock renderer derives from the structured definition:

```text
identity chip
summary card
full statblock
review editor
Plan and scene references
Play reference
combat drilldown
print view
agent context
embedding documents
```

The full statblock uses structured headers and the accepted `rules_text` of each element.
DungeonMindServer does not return canonical Markdown. Renderer version changes do not create
statblock revisions.

## 21. Representative fixtures

Contract fixtures must include:

1. a simple bruiser;
2. a spellcaster using slots;
3. an innate spellcaster;
4. a legendary creature with resource costs;
5. a lair creature;
6. nonstandard movement and movement qualifiers;
7. damage interactions with qualifiers and bypasses;
8. a warning-bearing definition;
9. a mythic or multi-phase creature;
10. a human-adjudicated unusual mechanic;
11. a revised statblock preserving element keys;
12. two distinct Threats sharing one statblock revision.

Fixtures should be committed as canonical JSON and exercised by Pydantic, OpenAPI,
Structured Outputs schema compilation, renderer derivation, and DungeonBuddy contract tests.

## 22. Implementation capability ladder

### A. Canonical models

Create a new model package independent of `statblock_models.py` and command-board draft models.

### B. Schema compilation

Publish OpenAPI and compile the same definition into a strict provider schema.

### C. Candidate generation

Reuse generation infrastructure behind the new request and definition shape.

### D. Validation

Implement layered validation and stable issue codes.

### E. Revision store

Create logical statblocks and immutable revision persistence with canonical digests.

### F. Read routes

Return exact revisions and revision history.

### G. Generated DungeonBuddy client

Generate transport types/client from DungeonMindServer OpenAPI.

### H. DungeonBuddy projection and combat adapter

Render summaries/full sheets and add exact revisions to the existing tracker.

### I. Revision authoring workflow

Accept DungeonBuddy-edited complete definitions and append validated revisions.

## 23. Acceptance criteria

The contract design is successfully implemented when:

- one Pydantic `StatblockDefinitionV1` is the semantic shape used for Structured Outputs,
  API editing, validation, rendering, and persistence;
- the OpenAI provider returns no server-owned identity or lifecycle fields;
- every accepted revision is immutable and retrievable by exact ID;
- the same accepted revision produces the same mechanics after transport, storage, reload,
  rendering, and combat seeding;
- a rules-element key survives a non-destructive revision;
- a mythic phase is represented through explicit known structures;
- an unusual unsupported mechanic is preserved as `human_adjudicated` rather than discarded;
- no old route or old project shape is required by the new contract;
- DungeonBuddy consumes generated contract types rather than a copied schema;
- no mutable mechanics field has two service owners.

## 24. Explicitly superseded assumptions

For the DungeonBuddy integration, this document supersedes assumptions that:

- the v2 command-board draft envelope should become the durable contract;
- Markdown is the canonical statblock payload;
- `CombatDefaults` should be copied across the service boundary;
- the current `Action` type is sufficient;
- DungeonBuddy owns or duplicates the statblock schema;
- current StatBlockGenerator project documents are immutable revisions;
- backwards compatibility with existing generator consumers is required.

Those predecessor routes may continue serving their current clients until separately retired.
They are not adapters, dependencies, or acceptance gates for this contract.
