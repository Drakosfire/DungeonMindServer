"""Versioned, definition-only prompts for structured statblock generation."""
from __future__ import annotations

from statblocks_v1.application.commands import GenerateStatblockCommandV1, ReviseStatblockCommandV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

PROMPT_VERSION = "statblock-generation-prompt-v2"


def build_system_prompt(edition: str) -> str:
    edition_guidance = (
        "Use 2014 D&D 5e terminology and conventions."
        if edition == "2014"
        else "Use 2024 D&D 5e terminology and conventions; do not mix 2014-only wording unless necessary."
    )
    return f"""You are a D&D 5e {edition} creature designer. You emit exactly one
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
"""


def build_generation_prompt(command: GenerateStatblockCommandV1) -> str:
    intent = _intent_block(command.intent)
    context = _context_block(command.context)
    parts = [
        f"Create one creature named {command.source.name_hint!r}.",
        "Source description:",
        command.source.description,
    ]
    if intent:
        parts.append(intent)
    if context:
        parts.append(context)
    return "\n".join(parts) + "\n"


def build_revision_prompt(
    command: ReviseStatblockCommandV1, source: StatblockDefinitionV1
) -> str:
    preservation = (
        "Preserve existing rule-element local keys whenever their conceptual rule remains."
        if command.preserve_element_keys
        else "You may replace local keys when replacing the corresponding conceptual rule."
    )
    intent = _intent_block(command.intent)
    context = _context_block(command.context)
    parts = [
        f"Revise this exact source definition according to: {_items(command.revision_instructions)}.",
        preservation,
    ]
    if intent:
        parts.append(intent)
    if context:
        parts.append(context)
    if command.source is not None:
        parts.extend(
            [
                f"Updated authored description ({command.source.name_hint!r}):",
                command.source.description,
            ]
        )
    parts.extend(
        [
            "Return a complete replacement definition, with no wrapper or commentary.",
            "Source definition JSON:",
            source.model_dump_json(exclude_none=False),
        ]
    )
    return "\n".join(parts) + "\n"


def _intent_block(intent) -> str:
    parts: list[str] = []
    if intent.target_cr:
        parts.append(f"target CR={intent.target_cr}")
    if intent.roles:
        parts.append(f"roles={_items(intent.roles)}")
    if intent.complexity:
        parts.append(f"complexity={intent.complexity}")
    if intent.must_include:
        parts.append(f"must include={_items(intent.must_include)}")
    if intent.must_avoid:
        parts.append(f"must avoid={_items(intent.must_avoid)}")
    if not parts:
        return ""
    return "Intent: " + ", ".join(parts) + "."


def _context_block(context) -> str:
    parts: list[str] = []
    if context.party_level is not None:
        parts.append(f"party level={context.party_level}")
    if context.party_size is not None:
        parts.append(f"party size={context.party_size}")
    if context.terrain_notes:
        parts.append(f"terrain={_items(context.terrain_notes)}")
    if not parts:
        return ""
    return "Encounter context: " + ", ".join(parts) + "."


def _items(values: list[str]) -> str:
    return ", ".join(values) if values else "none"
