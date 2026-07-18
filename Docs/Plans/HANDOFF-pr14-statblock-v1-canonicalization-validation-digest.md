# HANDOFF — PR14 Statblock v1 canonicalization, validation, and digest

**Status:** READY AFTER PR13  
**Target repository:** `Drakosfire/DungeonMindServer`  
**Predecessor:** PR13 contract models and fixtures  
**Successor:** `HANDOFF-pr15-statblock-v1-repositories-persistence.md`

## PR13 predecessor completion notes

- Canonical models live in `statblocks_v1/domain/primitives.py`,
  `profiles.py`, and `rule_elements.py`; the public root is
  `StatblockDefinitionV1`.
- Mechanic discriminator variants are `AttackMechanic`, `SaveEffectMechanic`,
  `MultiattackMechanic`, `SpellcastingMechanic`, `PassiveMechanic`,
  `CompositeMechanic`, `PhaseTransitionMechanic`, and
  `HumanAdjudicatedMechanic`. The implementation follows the design names,
  intentionally superseding the earlier handoff's movement/utility names.
- **Proficiency bonus is authored only on `challenge.proficiency_bonus`** —
  not duplicated on `ProficiencyProfile`.
- `Usage.recharge_range` is a `{minimum, maximum}` object (`RechargeRange`),
  not a tuple (OpenAI-strict safe).
- `SpellRef` includes `level` and `school` in addition to `name` / `rules_text`.
- Schema compiler (`statblocks_v1/domain/schema.py`) strips metadata
  context-aware (preserves property names `default` / `description`),
  rewrites `oneOf` → `anyOf`, and rejects `prefixItems`.
- Pydantic canonical and OpenAI strict artifacts are deterministic JSON at
  `statblocks_v1/domain/schema_artifacts/statblock_definition_v1.{canonical,openai-strict}.schema.json`.
- Fixtures are under `Docs/Design/fixtures/dungeonbuddy-statblock-v1/`.
  Cross-reference and action-economy invalid examples intentionally remain
  structurally parseable for this PR and are validation work for PR14.
- Focused tests: `./scripts/run_statblocks_v1_tests.sh` (isolated runner).
- PR14 must enforce local-key uniqueness, default armor-class cardinality,
  multiattack/phase/resource references, section/activation coherence,
  ruleset policy, and all cross-field rules listed below.

## 0. Mission

Implement the pure-domain trust core that turns any structurally valid `StatblockDefinitionV1` into a deterministic validation outcome, canonical representation, and content digest.

This layer governs model-generated definitions, DungeonBuddy-edited definitions, and persisted revisions equally.

## 1. Required services

Implement pure services or functions for:

```text
canonicalize_definition(definition)
validate_definition(definition, mode)
compute_definition_digest(canonical_definition)
```

The exact API may differ, but HTTP routes, OpenAI providers, and repositories must call the same domain behavior.

## 2. Validation levels

Define explicit levels rather than one boolean `is_valid`.

Recommended outcome:

```text
structural validity
reference validity
rules consistency
persistence readiness
warnings
errors
```

Suggested modes:

```text
generation_candidate
editor_preview
persistence
```

Persistence mode is strictest. Candidate mode may preserve warning-bearing definitions for human review but may not permit structurally incoherent mechanics.

## 3. Required validation rules

At minimum:

### Identity and profile rules

- exactly one default armor-class profile;
- HP method matches required fields;
- ability-score ranges are enforced;
- CR serialization is valid for selected ruleset;
- proficiency bonus and XP agree with ruleset unless an explicit override is declared;
- passive Perception agrees with inputs or declares override semantics.

### Local identity and references

- keys are unique in their namespace;
- multiattack references existing rule elements;
- phase transitions reference existing phases/elements/resources;
- resource costs reference existing pools;
- enabled/disabled element sets do not conflict;
- no cyclic reference pattern that the contract forbids.

### Section and action economy

- section and activation are coherent;
- legendary action costs require an appropriate resource pool;
- lair elements require lair context and valid timing;
- reaction activation includes a trigger/timing expression;
- passive traits do not consume an action unless explicitly special.

### Mechanics

- attack mechanic has valid target and range/reach;
- save effect has ability and DC/derivation;
- damage expressions are valid;
- usage/recharge fields are coherent;
- spellcasting group usage is coherent;
- automation support does not claim full support for a human-adjudicated mechanic.

### Typed semantics and rules text

Implement a bounded contradiction checker for clear mismatches, not a general natural-language theorem prover.

Examples worth detecting:

- typed attack bonus differs from a clearly parseable `+N to hit` in `rules_text`;
- typed save DC differs from a clearly parseable `DC N`;
- typed damage dice/type differs from a simple parseable damage clause;
- element named as reaction but rendered text says “as an action,” where unambiguous.

Return warnings when parsing is uncertain. Block persistence only on material, high-confidence contradictions defined by policy.

## 4. Canonicalization

Define a versioned canonicalization policy.

It must specify:

- canonical JSON field ordering;
- Unicode normalization;
- whitespace treatment in strings;
- preservation of `rules_text` content;
- omitted versus explicit null/empty behavior;
- ordering of semantic lists such as rule elements and spell groups;
- normalization of non-semantic sets such as tags where appropriate;
- dice expression serialization;
- CR fraction serialization;
- numeric representation;
- contract/canonicalizer version included in digest preimage or receipt.

Do not sort lists whose order controls presentation, multiattack sequence, phase sequence, or effect execution.

## 5. Digest

Use a documented cryptographic digest such as SHA-256 over canonical UTF-8 JSON.

The digest should cover the complete canonical mechanics definition, including accepted `rules_text` and reusable `flavor_text`.

It should not cover:

- statblock/revision IDs;
- timestamps;
- candidate or validation receipts;
- DungeonBuddy graph fields;
- mutable preferred image selection;
- transport wrapper fields.

Return a namespaced value such as:

```text
sha256:<hex>
```

## 6. Validation receipt

Define a stable `ValidationReceiptV1` containing at least:

```text
status
mode
validator_version
canonicalizer_version
issues[]
definition_digest
validated_at  # envelope fact supplied by caller/clock, not digest input
```

Issues need stable codes, severity, field/reference locations, and human-readable messages.

## 7. Determinism requirements

Tests must prove:

- the same definition produces byte-identical canonical JSON;
- repeated validation produces equivalent receipts except caller-supplied time;
- semantically equivalent non-semantic ordering normalizes identically;
- presentation/semantic order remains distinct when order matters;
- changing one mechanic or rules-text value changes the digest;
- server envelope metadata does not change the digest.

## 8. Suggested files

```text
statblocks_v1/domain/canonicalization.py
statblocks_v1/domain/validation.py
statblocks_v1/domain/digests.py
statblocks_v1/domain/receipts.py
tests/statblocks_v1/test_canonicalization.py
tests/statblocks_v1/test_validation.py
tests/statblocks_v1/test_digests.py
```

## 9. Testing requirements

Use all PR13 fixtures plus focused mutation tests.

Required cases:

- every valid fixture is persistence-ready or has intentionally documented warnings;
- every invalid cross-reference fixture produces the expected stable issue code;
- obvious rules-text contradiction behavior is tested;
- human-adjudicated fixture remains valid and reports manual automation support honestly;
- digest snapshot is checked for at least three fixtures;
- no external SDK is imported.

## 10. Acceptance criteria

PR14 is complete when:

- persistence readiness is a pure-domain decision;
- digest calculation is versioned and deterministic;
- canonicalization policy is documented in code and tests;
- validation issue codes are stable enough for DungeonBuddy UI use;
- no route or repository duplicates the trust rules;
- all focused tests run.

## 11. Non-goals

- no Firestore;
- no candidate storage;
- no OpenAI calls;
- no HTTP routes;
- no full CR simulation engine;
- no attempt to parse every possible rules-text sentence.

## 12. Successor handoff

Before merge, update PR15 with:

- canonical JSON API and version;
- digest format;
- persistence-readiness invocation;
- validation receipt model/path;
- stable issue-code catalog;
- immutable fields the repository must store exactly.
