"""Adapter helpers for StatBlockGenerator v2 command-board drafts."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Union
from uuid import uuid4

from statblockgenerator.models.command_board_contract_models import (
    CombatDefaults,
    DraftProvenance,
    ReviewWarning,
    StatBlockDraft,
    StatBlockDraftRequest,
)
from statblockgenerator.models.statblock_models import CreatureGenerationRequest, StatBlockDetails

DC_PATTERN = re.compile(r"\bDC\s+(\d{1,2})\b", re.IGNORECASE)


def build_generation_request(request: StatBlockDraftRequest) -> CreatureGenerationRequest:
    """Convert a v2 command-board request into the current generator request."""

    description = compose_generation_description(request)
    return CreatureGenerationRequest(
        description=description,
        challenge_rating_target=request.intent.target_cr,
        include_spells=False,
        include_legendary=False,
        include_lair=False,
    )


def compose_generation_description(request: StatBlockDraftRequest) -> str:
    """Compose a transparent prompt for the existing StatBlockGenerator core."""

    lines = [
        f"Mode: {request.mode}",
        f"Intent: {request.intent.summary}",
    ]
    if request.intent.target_cr is not None:
        lines.append(f"Target CR: {request.intent.target_cr}")
    if request.intent.target_role:
        lines.append(f"Role: {request.intent.target_role}")
    if request.intent.tone:
        lines.append(f"Tone: {request.intent.tone}")
    if request.intent.complexity:
        lines.append(f"Complexity: {request.intent.complexity}")
    if request.prompt:
        lines.append(f"Prompt: {request.prompt}")

    if request.encounter_context:
        context = request.encounter_context
        encounter_bits = []
        if context.party_level is not None:
            encounter_bits.append(f"party level {context.party_level}")
        if context.party_size is not None:
            encounter_bits.append(f"party size {context.party_size}")
        if context.round is not None:
            encounter_bits.append(f"round {context.round}")
        if context.threat_pressure:
            encounter_bits.append(f"threat pressure {context.threat_pressure}")
        if context.objective:
            encounter_bits.append(f"objective: {context.objective}")
        if encounter_bits:
            lines.append("Encounter context: " + "; ".join(encounter_bits))

    if request.terrain_context:
        terrain = request.terrain_context
        if terrain.summary:
            lines.append(f"Terrain context: {terrain.summary}")
        if terrain.features:
            lines.append("Terrain features: " + ", ".join(terrain.features))
        if terrain.hazards:
            lines.append("Terrain hazards: " + ", ".join(terrain.hazards))
        if terrain.constraints:
            lines.append("Terrain constraints: " + "; ".join(terrain.constraints))

    if request.revision_instructions:
        lines.append("Revision instructions: " + "; ".join(request.revision_instructions))

    if request.source_statblock:
        source = request.source_statblock
        if isinstance(source, StatBlockDetails):
            source_name = source.name
        else:
            source_name = str(source.get("name", "provided source statblock"))
        lines.append(f"Source statblock: {source_name}")

    return "\n".join(lines)


def coerce_statblock(statblock_data: Union[StatBlockDetails, Dict[str, Any]]) -> StatBlockDetails:
    """Coerce generator output into the structured StatBlockDetails model."""

    if isinstance(statblock_data, StatBlockDetails):
        return statblock_data
    return StatBlockDetails.model_validate(statblock_data)


def render_markdown(statblock: StatBlockDetails) -> str:
    """Render a conservative markdown statblock for command-board preview."""

    lines = [
        f"# {statblock.name}",
        f"*{statblock.size.value} {statblock.type.value}, {statblock.alignment.value}*",
        "",
        f"**Armor Class** {statblock.armor_class}",
        f"**Hit Points** {statblock.hit_points} ({statblock.hit_dice})",
        f"**Speed** {speed_summary(statblock)}",
        "",
        "|STR|DEX|CON|INT|WIS|CHA|",
        "|---:|---:|---:|---:|---:|---:|",
        (
            f"|{statblock.abilities.str} ({format_modifier(statblock.abilities.get_modifier('str'))})"
            f"|{statblock.abilities.dex} ({format_modifier(statblock.abilities.get_modifier('dex'))})"
            f"|{statblock.abilities.con} ({format_modifier(statblock.abilities.get_modifier('con'))})"
            f"|{statblock.abilities.intelligence} ({format_modifier(statblock.abilities.get_modifier('int'))})"
            f"|{statblock.abilities.wis} ({format_modifier(statblock.abilities.get_modifier('wis'))})"
            f"|{statblock.abilities.cha} ({format_modifier(statblock.abilities.get_modifier('cha'))})|"
        ),
        "",
    ]

    if statblock.saving_throws:
        lines.append("**Saving Throws** " + format_bonus_map(statblock.saving_throws))
    if statblock.skills:
        lines.append("**Skills** " + format_bonus_map(statblock.skills))
    if statblock.damage_resistance:
        lines.append(f"**Damage Resistances** {statblock.damage_resistance}")
    if statblock.damage_immunity:
        lines.append(f"**Damage Immunities** {statblock.damage_immunity}")
    if statblock.condition_immunity:
        lines.append(f"**Condition Immunities** {statblock.condition_immunity}")
    if statblock.damage_vulnerability:
        lines.append(f"**Damage Vulnerabilities** {statblock.damage_vulnerability}")

    lines.extend(
        [
            f"**Senses** {senses_summary(statblock) or 'passive Perception ' + str(statblock.senses.passive_perception)}",
            f"**Languages** {statblock.languages}",
            f"**Challenge** {statblock.challenge_rating} ({statblock.xp:,} XP)",
            "",
        ]
    )

    append_action_section(lines, "Traits", statblock.special_abilities)
    append_action_section(lines, "Actions", statblock.actions)
    append_action_section(lines, "Bonus Actions", statblock.bonus_actions)
    append_action_section(lines, "Reactions", statblock.reactions)

    if statblock.description:
        lines.extend(["## Description", statblock.description])

    return "\n".join(lines).strip()


def derive_combat_defaults(statblock: StatBlockDetails) -> CombatDefaults:
    """Derive command-board combat defaults from the statblock only."""

    return CombatDefaults(
        name=statblock.name,
        armor_class=statblock.armor_class,
        hit_points=statblock.hit_points,
        initiative_bonus=statblock.abilities.get_modifier("dex"),
        passive_perception=statblock.senses.passive_perception if statblock.senses else None,
        speed_summary=speed_summary(statblock),
        primary_actions=[action.name for action in statblock.actions[:4]],
        save_dcs=extract_save_dcs(statblock),
        senses_summary=senses_summary(statblock),
        condition_immunities=statblock.condition_immunity,
        suggested_tactics=suggest_tactics(statblock),
    )


def build_warnings(
    request: StatBlockDraftRequest,
    statblock: StatBlockDetails,
    markdown: str,
    validation_warnings: Optional[Iterable[Any]] = None,
) -> List[ReviewWarning]:
    """Build lightweight command-board review warnings."""

    warnings: List[ReviewWarning] = []

    if request.intent.target_cr is not None and normalize_cr(request.intent.target_cr) != normalize_cr(statblock.challenge_rating):
        warnings.append(
            ReviewWarning(
                code="cr_mismatch",
                message=(
                    f"Requested target CR {request.intent.target_cr}, but generated statblock is "
                    f"CR {statblock.challenge_rating}."
                ),
            )
        )

    if request.terrain_context and not statblock_mentions_terrain(statblock, request.terrain_context.features):
        warnings.append(
            ReviewWarning(
                code="terrain_assumption",
                message="Terrain context was provided, but generated statblock text does not reference terrain features.",
            )
        )

    if request.output_options.include_markdown and not markdown.strip():
        warnings.append(
            ReviewWarning(
                code="missing_markdown",
                message="Markdown rendering failed or produced an empty draft.",
                severity="error",
            )
        )

    for warning in validation_warnings or []:
        warnings.append(
            ReviewWarning(
                code="validation_warning",
                message=str(warning),
            )
        )

    return warnings


def build_draft(
    request: StatBlockDraftRequest,
    statblock_data: Union[StatBlockDetails, Dict[str, Any]],
    generation_info: Optional[Dict[str, Any]] = None,
    validation_warnings: Optional[Iterable[Any]] = None,
) -> StatBlockDraft:
    """Build the stable v2 draft envelope from generator output."""

    statblock = coerce_statblock(statblock_data)
    markdown = render_markdown(statblock) if request.output_options.include_markdown else ""
    combat_defaults = derive_combat_defaults(statblock)
    warnings = build_warnings(request, statblock, markdown, validation_warnings)
    emitted_warnings = warnings if request.output_options.include_review_warnings else []
    review_status = "warnings" if emitted_warnings else "needs_dm_review"

    return StatBlockDraft(
        draft_id=f"draft-{request.request_id or uuid4().hex}",
        lifecycle_state="live_draft",
        review_status=review_status,
        statblock=statblock,
        markdown=markdown,
        combat_defaults=combat_defaults,
        warnings=emitted_warnings,
        provenance=DraftProvenance(
            request_id=request.request_id,
            mode=request.mode,
            source_refs=request.source_refs,
            generated_at=datetime.now(timezone.utc).isoformat(),
            persist_requested=request.output_options.persist,
            generation_info=generation_info or {},
        ),
    )


def append_action_section(lines: List[str], title: str, actions: Optional[List[Any]]) -> None:
    if not actions:
        return
    lines.append(f"## {title}")
    for action in actions:
        lines.append(f"**{action.name}.** {action.desc}")
    lines.append("")


def speed_summary(statblock: StatBlockDetails) -> str:
    speeds = statblock.speed
    parts = []
    for label in ("walk", "fly", "swim", "climb", "burrow"):
        value = getattr(speeds, label)
        if value is None:
            continue
        prefix = "" if label == "walk" else f"{label} "
        parts.append(f"{prefix}{value} ft.")
    return ", ".join(parts) or "0 ft."


def senses_summary(statblock: StatBlockDetails) -> Optional[str]:
    senses = statblock.senses
    if not senses:
        return None
    parts = []
    for label in ("darkvision", "blindsight", "tremorsense", "truesight"):
        value = getattr(senses, label)
        if value is not None:
            parts.append(f"{label} {value} ft.")
    parts.append(f"passive Perception {senses.passive_perception}")
    return ", ".join(parts)


def extract_save_dcs(statblock: StatBlockDetails) -> List[int]:
    text_blocks = []
    for action_list in (
        statblock.special_abilities,
        statblock.actions,
        statblock.bonus_actions,
        statblock.reactions,
    ):
        if action_list:
            text_blocks.extend(action.desc for action in action_list)
    if statblock.spells:
        text_blocks.append(f"DC {statblock.spells.save_dc}")

    dcs = {int(match.group(1)) for text in text_blocks for match in DC_PATTERN.finditer(text or "")}
    return sorted(dcs)


def statblock_mentions_terrain(statblock: StatBlockDetails, features: List[str]) -> bool:
    if not features:
        return True
    searchable = " ".join(
        [
            statblock.name,
            statblock.description,
            *(action.name + " " + action.desc for action in statblock.actions),
            *(action.name + " " + action.desc for action in statblock.special_abilities or []),
            *(action.name + " " + action.desc for action in statblock.bonus_actions or []),
            *(action.name + " " + action.desc for action in statblock.reactions or []),
        ]
    ).lower()
    return any(feature.lower() in searchable for feature in features)


def suggest_tactics(statblock: StatBlockDetails) -> List[str]:
    tactics = []
    if statblock.actions:
        tactics.append(f"Open with {statblock.actions[0].name} when the target is in range.")
    if statblock.bonus_actions:
        tactics.append(f"Use {statblock.bonus_actions[0].name} as a bonus action when available.")
    if statblock.reactions:
        tactics.append(f"Reserve reaction for {statblock.reactions[0].name}.")
    return tactics[:3]


def format_bonus_map(values: Dict[str, int]) -> str:
    return ", ".join(f"{key} {format_modifier(value)}" for key, value in values.items())


def format_modifier(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def normalize_cr(value: Union[str, float, int]) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return float(numerator) / float(denominator)
    return float(text)
