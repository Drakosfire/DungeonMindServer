# HANDOFF — PR26 statblock generation prompt and schema guidance

## Mission

Move statblock generation guidance out of one 8-line prose blob and into the two
channels the model actually reads — **schema field descriptions** (field-local
invariants) and a **system message** (cross-field conventions) — so that
domain-validator violations stop reaching the operator as editable-but-wrong
candidates.

Post-`b645019`, domain-invalid output is no longer a terminal failure; it is GM
toil in the Workbench. Every avoided validator error is avoided hand-editing.

## Evidence this is built on (already gathered — do not re-derive)

1. **`description` is accepted by OpenAI Structured Outputs in `strict` mode.**
   Confirmed by 20 live calls against `gpt-5.6-luna` on 2026-07-29: bare schema
   and description-bearing schema were both accepted, zero rejections. The
   comment at `statblocks_v1/domain/schema.py:19` claiming these keys are "not
   accepted" is **wrong** for `description`.
   - Corroboration: the shipped strict artifact already retains `pattern` and
     `minimum` (`Usage.resource_key`, `Usage.uses`), which were also historically
     unsupported and evidently are not. The allowlist was written once against an
     older API and never re-validated.
2. **The channel question is NOT settled.** On a toy one-convention probe
   (`exactly one AC default`, 5 trials/arm): bare 4/5, schema-description 5/5,
   prompt-rule 5/5, both 5/5. The probe was too easy to discriminate. An earlier
   3-trial run showed 0/3 for the description arm and was pure noise — **use
   N ≥ 5**. This is why Slice 3 (harness) exists and why we ship both channels.
3. **`request_digest` does not hash prompt text.** It is computed from the
   request payload (`compute_generate_candidate_digest`). Restructuring prompts
   therefore cannot disturb idempotency or replay. `prompt_version` on
   `GenerationReceiptV1` carries provenance; bump it.
4. **Validator density** (`statblocks_v1/domain/validation.py`): 43 distinct
   codes across 73 emit sites. `USAGE_FIELDS_INCOHERENT` alone is 16 sites — the
   dominant cluster and one of the three live dogfood failures.
5. **Live dogfood baseline (Mireward Latchling, 2026-07-29)** produced exactly
   three error-severity codes:
   `DEFAULT_ARMOR_CLASS_CARDINALITY`, `HUMAN_ADJUDICATED_AUTOMATION_MISMATCH`,
   `USAGE_FIELDS_INCOHERENT`.
6. **Every test asserts `len(provider.calls)`; none index the tuple.** Widening
   `FakeDefinitionProvider.calls` is safe.

## Slices

Slices are independent and may land as separate commits on one branch. Slice 3
should land **first** if you want a measured baseline before changing behavior.

---

### Slice 1 — Unlock and populate the schema channel

**Files in scope**

```
statblocks_v1/domain/schema.py
statblocks_v1/domain/primitives.py
statblocks_v1/domain/profiles.py
statblocks_v1/domain/rule_elements.py
statblocks_v1/domain/schema_artifacts/statblock_definition_v1.canonical.schema.json
statblocks_v1/domain/schema_artifacts/statblock_definition_v1.openai-strict.schema.json
openapi/dungeonbuddy-statblocks-v1.json
generated/dungeonbuddy-statblocks-v1/client.ts
Docs/Design/fixtures/dungeonbuddy-statblock-v1-api/candidate-response.json
Docs/Design/fixtures/dungeonbuddy-statblock-v1-api/revise-replay-response.json
tests/statblocks_v1/test_schema_snapshots.py
```

**Change 1.1** — in `schema.py`, stop stripping `description`. Keep stripping
everything else, **including `title`**: Pydantic auto-generates titles from class
names, they duplicate the `$defs` key, and they are pure token cost. Rename the
constant to reflect what it now means (e.g. `_STRIPPED_OPENAI_METADATA`) and
**replace the incorrect comment** with the empirical finding from Evidence §1.

Resulting strip set: `$schema`, `default`, `examples`, `discriminator`, `title`.

**Change 1.2** — add `Field(description=...)` to exactly these fields. Use this
text verbatim; it is written to match the validators in `validation.py`.

| Model / field | `description` |
|---|---|
| `Usage.kind` | `Determines which sibling fields are allowed. recharge: recharge_range required, uses and resource_key null. at_will: all three null. per_turn/per_round/per_day: uses required, others null. once: uses null or 1, others null. resource: resource_key required, uses null. spell_slots: leveled spell groups only, uses and resource_key null. manual: recharge_range null, others optional.` |
| `Usage.recharge_range` | `Only for kind 'recharge'; must be null for every other kind.` |
| `Usage.uses` | `Required for per_turn, per_round, and per_day. For 'once' it is null or exactly 1. Must be null for at_will, recharge, resource, and spell_slots.` |
| `Usage.resource_key` | `Required for kind 'resource' and must name a declared resources[].key. Must be null for every other kind.` |
| `ResourceCost.resource_key` | `Must name a declared resources[].key. A pool may appear at most once per element, and combined costs must not exceed that pool's maximum.` |
| `ArmorClassProfile.default` | `Exactly one profile in defenses.armor_classes must set true; all others false.` |
| `CreaturePhase.default` | `Exactly one phase must set true whenever phases are present.` |
| `RuleElement.automation_support` | `Must be 'manual' when mechanic.kind is 'human_adjudicated'.` |
| `HitPointProfile.method` | `'formula' sets formula and leaves fixed_value null; 'fixed' sets fixed_value and leaves formula null.` |
| `HitPointProfile.displayed_average` | `When set, must equal the average of the typed formula.` |
| `ChallengeProfile.proficiency_bonus` | `Must match rating on the standard 5e challenge-rating table.` |
| `SenseProfile.passive_perception` | `Must equal 10 + the Perception skill value when proficiencies.skills contains a Perception entry.` |
| `SkillBonus.derivation` | `'standard' means value equals ability modifier plus proficiency bonus; 'expertise' adds proficiency twice; use 'explicit_override' for any other value.` |
| `SavingThrowBonus.derivation` | `'standard' means value equals ability modifier plus proficiency bonus; 'expertise' adds proficiency twice; use 'explicit_override' for any other value.` |

Do **not** add descriptions beyond this table in this slice. Scope is the
high-density validator surface only.

**Change 1.3** — update `test_schema_snapshots.py`:
`test_openai_strict_schema_closes_objects_and_strips_node_metadata` currently
enforces that `description` is stripped. Invert that for `description` only;
keep asserting the rest are stripped. Add a test asserting the strict artifact
carries a description at each of these paths (guards against silent loss):
`Usage.kind`, `Usage.uses`, `Usage.resource_key`, `ArmorClassProfile.default`,
`RuleElement.automation_support`.

**Change 1.4** — regenerate every derived artifact. Descriptions flow into the
canonical schema, the strict schema, **the schema fingerprint**, the OpenAPI
spec, the TS client, and the two API fixtures that embed a fingerprint. All of
them must be regenerated in the same commit or the compiler's staleness check
(`compile_openai_definition_schema`) will fail closed at runtime.

**Report** the strict artifact token delta (compact JSON bytes ÷ 4, before and
after). If the delta exceeds +1200 tokens, stop and report rather than trimming
the table yourself.

---

### Slice 2 — Restructure prompts into system + user

**Files in scope**

```
statblocks_v1/application/prompts.py
statblocks_v1/application/provider.py
statblocks_v1/application/generation.py
statblocks_v1/infrastructure/openai_provider.py
statblocks_v1/infrastructure/fake_provider.py
tests/statblocks_v1/test_prompt_builder.py
tests/statblocks_v1/integration/test_openai_generation.py
```

**Change 2.1** — `prompts.py` gains `build_system_prompt(edition: str) -> str`
returning the block below verbatim (with `{edition}` and `{edition_guidance}`
interpolated exactly as `_base_prompt` does today). Delete `_base_prompt` and
remove its content from the user-message builders — `build_generation_prompt`
and `build_revision_prompt` now return **task data only** (creature name,
description, revision instructions, preservation clause, intent, context, source
definition JSON).

```text
You are a D&D 5e {edition} creature designer. You emit exactly one
StatblockDefinitionV1 JSON object and nothing else.
{edition_guidance}

STRUCTURE
- definition.ruleset.system and definition.ruleset.edition must exactly match the requested ruleset.
- Never emit candidate IDs, timestamps, digests, provenance, assets, Markdown, or any outer envelope.
- Every definition-local `key` is a stable lowercase identifier matching ^[a-z][a-z0-9_]*$, unique within its collection, and referenced by other elements.
- `section` is where a rule appears (trait/action/reaction/etc.); `activation` is how it is used; `mechanic.kind` is its typed behavior.
- Provide complete table-facing `rules_text` for every rule element even when typed mechanics are present, and keep its numbers consistent with the typed mechanic (attack bonus, damage dice, save DC).

CARDINALITY
- defenses.armor_classes: exactly one profile has default=true; all others false.
- phases, when present: exactly one phase has default=true.

USAGE FIELDS - usage.kind decides which sibling fields may appear:
  recharge                       recharge_range REQUIRED (ordered d6); uses and resource_key null
  at_will                        recharge_range, uses, resource_key all null
  per_turn / per_round / per_day uses REQUIRED; recharge_range and resource_key null
  once                           uses null or exactly 1; recharge_range and resource_key null
  resource                       resource_key REQUIRED (a declared pool); uses null
  spell_slots                    leveled spell groups only; uses and resource_key null
  manual                         recharge_range null; uses and resource_key optional
Never set recharge_range on any kind other than recharge.

DERIVED MATH - these are checked arithmetically:
- challenge.proficiency_bonus must match challenge.rating on the standard 5e table.
- senses.passive_perception must equal 10 + the Perception skill value when a Perception skill entry exists.
- Skills and saves with derivation "standard" equal ability modifier + proficiency bonus; "expertise" adds proficiency twice; use "explicit_override" for anything else.
- vitality.hit_points: method "formula" sets formula and leaves fixed_value null; method "fixed" sets fixed_value and leaves formula null. displayed_average, when set, equals the formula average.

REFERENCES - declare before you reference:
- Multiattack sequences reference other rule_elements keys; a multiattack may not reference itself or another multiattack.
- usage.resource_key, costs[].resource_key, and spell-group usage must name a declared resources[].key.
- Combined costs against one pool must not exceed its maximum, and a pool may appear at most once in one element's costs.
- Legendary actions require usage.resource_key plus at least one cost, all pointing at the same declared pool.
- Lair actions require a lair profile and an initiative timing expression.

ATTACKS
- Melee attacks set mechanic.reach and must not set mechanic.range; ranged attacks set mechanic.range and must not set mechanic.reach. Long range uses the same unit and is >= normal range.
- Attack targets never set range. A "creatures" target requires count; a single creature target omits count or sets 1; a self target omits count; an area target requires area.

ESCAPE HATCH
- When a mechanic cannot be represented by the typed contract, set mechanic.kind "human_adjudicated" AND automation_support "manual". Never invent fields.

BEFORE RETURNING, verify:
1. Exactly one armor class has default=true.
2. Every usage object matches its kind's row above.
3. Every key you reference is declared somewhere in the definition.
4. proficiency_bonus matches CR, and passive_perception matches Perception.
5. Every human_adjudicated mechanic has automation_support "manual".
```

**Change 2.2** — the intent/context blocks currently emit bare data with filler
defaults (`target CR=use the description`, `complexity=appropriate`). Omit a
line entirely when the value is unset rather than emitting a filler word.

**Change 2.3** — `DefinitionProvider.generate_definition` gains a keyword-only
`system: str`. `OpenAIDefinitionProvider` sends it as the system message and
**drops** the current `"Return only the requested JSON schema instance."`, which
duplicates what `strict: true` enforces mechanically.
`FakeDefinitionProvider` records it (widen `calls` to a 4-tuple and the
`callback` signature to match). `generation.py` passes
`build_system_prompt(intent.ruleset.edition.value)`.

**Change 2.4** — bump `PROMPT_VERSION` to `statblock-generation-prompt-v2`.

**Change 2.5** — update `test_prompt_builder.py` for the split: assert the
system prompt carries the conventions (usage matrix, cardinality, escape hatch
naming `automation_support`) and that the user prompt carries only task data and
**no longer** contains the persona/envelope lines. Update the two live-API call
sites in `tests/statblocks_v1/integration/test_openai_generation.py` for the new
signature.

---

### Slice 3 — Falsification harness

**Files in scope**

```
scripts/statblock_prompt_eval.py            (new)
Docs/Design/fixtures/prompt-eval/*.json     (new, synthetic only)
```

A CLI that answers "did this actually reduce validator errors?" — the metric is
the **set of error-severity validator codes**, not a subjective read.

- For each (fixture × arm × trial): call the real provider, parse into
  `StatblockDefinitionV1`, run `validate_definition`, collect error-severity
  codes.
- Report per arm: trials, clean rate (zero error codes), and a frequency table
  of codes, plus total tokens and call count.
- **Arms are ablations owned by the harness, not flags in production code.**
  Build them by post-processing: `--arm bare` strips descriptions from the
  compiled schema *and* substitutes a minimal system message; `--arm schema-only`
  keeps descriptions, minimal system; `--arm prompt-only` strips descriptions,
  real system; `--arm both` is shipping config. Production code gets no test
  hooks.
- `--trials` defaults to **5** (Evidence §2: 3 is not enough).
- Ship two committed **synthetic** fixtures: one simple bruiser-shaped creature
  and one exercising legendary actions + spellcasting + recharge (the untested
  `LEGENDARY_RESOURCE_*` and `SPELL_GROUP_*` clusters).
- Accept `--description-file PATH` so the operator can run the real Mireward
  Latchling text locally. **Do not commit corpus creature text** — see
  `.cursor/rules/corpus-pii-and-llm-payloads.mdc`.
- Guard with the same opt-in env pattern as
  `tests/statblocks_v1/integration/test_openai_generation.py`; this must never
  run in CI.

---

### Slice 4 — Model policy alignment

**Files in scope**

```
MODEL_POLICY.json
.env.development
```

Structured generation targets **`gpt-5.4-mini`** (operator decision, 2026-07-29).
Point `actions.structured_generation` at `fast_smart_mini` and set
`STATBLOCKS_V1_OPENAI_MODEL` to `gpt-5.4-mini` so the policy default and the dev
override agree. Today they silently disagree: policy resolves to `gpt-5.4-nano`,
the env override runs `gpt-5.6-luna`, and prompt tuning validated on one does not
transfer to the other. **Never echo the `.env` contents** to logs or chat.

## Explicitly out of scope

- `statblocks_v1/domain/validation.py` — do not relax, reorder, or add
  validators. If a description and a validator disagree, the validator is
  authoritative; report the disagreement, do not "fix" either.
- `statblocks_v1/application/generation.py` beyond passing `system=` through.
  No retry logic, no re-prompting on validation failure, no candidate mutation.
- Diagnostics (`_SCHEMA_DIAGNOSTIC_MESSAGES`, `http_errors.py`,
  `candidate_operations.py`) — PR25 territory, settled, leave alone.
- Any Buddy-side change (`../DungeonMindBuddy/**`). Buddy's vendored models
  already render `validation_receipt` issues.
- Any other service package (`cardgenerator/`, `ruleslawyer/`,
  `statblockgenerator/`, `playercharactergenerator/`).
- Adding descriptions to fields not in the Slice 1 table.

## Verification (run these; paste real output)

```bash
cd /home/drakosfire/Projects/DungeonOverMind/DungeonMindServer

# Full statblocks_v1 suite — must be green. Baseline at b645019: 286 passed, 15 skipped.
uv run pytest tests/statblocks_v1 -q

# Isolated lane (pydantic pinned to 2.10.6 as of 8aff6ea)
./scripts/run_statblocks_v1_tests.sh

# Artifact staleness gate must pass (this is what fails closed in prod)
uv run python -c "from statblocks_v1.application.schema_compiler import compile_openai_definition_schema as c; s=c(); print(s.fingerprint)"

# Lint
uv run ruff check statblocks_v1 tests/statblocks_v1
```

For Slice 3, additionally paste one real harness run (`--arm both --trials 5`
against a committed synthetic fixture) showing the code-frequency table.

## Reporting contract

- `git diff --stat` filtered to **only the files you touched** — not the whole
  worktree.
- The strict-artifact token delta from Slice 1.
- Full pasted output of every verification command above.
- Any place a description in the Slice 1 table contradicted
  `validation.py`, quoted, with the validator line number — reported, not fixed.
