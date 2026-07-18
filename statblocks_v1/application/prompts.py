"""Versioned, definition-only prompts for structured statblock generation."""
from __future__ import annotations

from statblocks_v1.application.commands import GenerateStatblockCommandV1, ReviseStatblockCommandV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1

PROMPT_VERSION = "statblock-generation-prompt-v1"


def build_generation_prompt(command: GenerateStatblockCommandV1) -> str:
    return _base_prompt(command.ruleset.edition.value) + f"""
Create one creature named {command.source.name_hint!r}.
Source description:
{command.source.description}

Intent: target CR={command.intent.target_cr or "use the description"}, roles={_items(command.intent.roles)},
complexity={command.intent.complexity or "appropriate"}, must include={_items(command.intent.must_include)},
must avoid={_items(command.intent.must_avoid)}.
Encounter context: party level={command.context.party_level or "unspecified"}, party size={command.context.party_size or "unspecified"},
terrain={_items(command.context.terrain_notes)}.
"""


def build_revision_prompt(
    command: ReviseStatblockCommandV1, source: StatblockDefinitionV1
) -> str:
    preservation = (
        "Preserve existing rule-element local keys whenever their conceptual rule remains."
        if command.preserve_element_keys
        else "You may replace local keys when replacing the corresponding conceptual rule."
    )
    return _base_prompt(command.ruleset.edition.value) + f"""
Revise this exact source definition according to: {_items(command.revision_instructions)}.
{preservation}
Return a complete replacement definition, with no wrapper or commentary.
Source definition JSON:
{source.model_dump_json(exclude_none=False)}
"""


def _base_prompt(edition: str) -> str:
    edition_guidance = "Use 2014 D&D 5e terminology and conventions." if edition == "2014" else (
        "Use 2024 D&D 5e terminology and conventions; do not mix 2014-only wording unless necessary."
    )
    return f"""You produce only a StatblockDefinitionV1 JSON object for D&D 5e {edition}.
{edition_guidance}
Do not generate candidate IDs, timestamps, digests, provenance, assets, Markdown, or any outer envelope.
Every definition-local key is a stable lowercase identifier used by internal references. Keep them unique.
A section is where a rule appears (trait/action/reaction/etc.); activation is how it is used; mechanic.kind is its typed behavior.
Provide complete table-facing rules_text for every rule element even when typed mechanics are present.
When a mechanic cannot be represented safely by the typed contract, use mechanic.kind "human_adjudicated" and manual automation support; never invent fields.
"""


def _items(values: list[str]) -> str:
    return ", ".join(values) if values else "none"
