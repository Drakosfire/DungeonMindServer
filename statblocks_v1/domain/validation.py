"""Layered, deterministic validation for statblock v1 definitions."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import datetime

from statblocks_v1.domain.canonicalization import CANONICALIZER_VERSION
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.primitives import (
    ActivationKind,
    AutomationSupport,
    DamageEffect,
    DisableElementsEffect,
    EnableElementsEffect,
    EnterPhaseEffect,
    MovementEffect,
    ResourceChangeEffect,
    TargetKind,
    Usage,
    UsageKind,
)
from statblocks_v1.domain.receipts import (
    VALIDATOR_VERSION,
    ValidationIssueV1,
    ValidationMode,
    ValidationReceiptV1,
    ValidationSeverity,
    ValidationStatus,
)
from statblocks_v1.domain.rule_elements import (
    AttackMechanic,
    AttackType,
    CastingMode,
    HumanAdjudicatedMechanic,
    MultiattackMechanic,
    PhaseTransitionMechanic,
    RuleElement,
    RuleSection,
    SaveEffectMechanic,
    SpellcastingMechanic,
    SpellGroup,
    StatblockDefinitionV1,
)

IssueEmitter = Callable[[str, ValidationSeverity, str, str, str | None], None]

_CR_PROFICIENCY_BONUS = {
    "0": 2,
    "1/8": 2,
    "1/4": 2,
    "1/2": 2,
    **{str(cr): 2 for cr in range(1, 5)},
    **{str(cr): 3 for cr in range(5, 9)},
    **{str(cr): 4 for cr in range(9, 13)},
    **{str(cr): 5 for cr in range(13, 17)},
    **{str(cr): 6 for cr in range(17, 21)},
    **{str(cr): 7 for cr in range(21, 25)},
    **{str(cr): 8 for cr in range(25, 29)},
    **{str(cr): 9 for cr in range(29, 31)},
}
_SECTION_ACTIVATIONS = {
    RuleSection.action: {ActivationKind.action},
    RuleSection.bonus_action: {ActivationKind.bonus_action},
    RuleSection.reaction: {ActivationKind.reaction},
    RuleSection.legendary_action: {ActivationKind.legendary},
    RuleSection.lair_action: {ActivationKind.lair_initiative},
    RuleSection.trait: {
        ActivationKind.passive,
        ActivationKind.triggered,
        ActivationKind.special,
    },
    RuleSection.regional_effect: {
        ActivationKind.passive,
        ActivationKind.triggered,
        ActivationKind.special,
    },
}
_ATTACK_BONUS = re.compile(r"\+\s*(\d+)\s+to\s+hit\b", re.IGNORECASE)
_SAVE_DC = re.compile(r"\bDC\s*(\d+)\b", re.IGNORECASE)
_DAMAGE_CLAUSE = re.compile(
    r"\b(\d+)d(\d+)(?:\s*([+-])\s*(\d+))?\)\s+([a-z]+)\s+damage\b",
    re.IGNORECASE,
)
_LIMITED_USE_KINDS = frozenset(
    {UsageKind.per_turn, UsageKind.per_round, UsageKind.per_day}
)


def validate_definition(
    definition: StatblockDefinitionV1,
    mode: ValidationMode | str,
    *,
    validated_at: datetime | None = None,
) -> ValidationReceiptV1:
    """Validate a parsed definition without I/O or mutation.

    Candidate and preview validation preserve high-confidence text conflicts as
    warnings so a human can repair them. Persistence upgrades those conflicts
    to errors. Structural, reference, and action-economy incoherence is always
    an error in every mode.
    """

    validation_mode = ValidationMode(mode)
    issues: list[ValidationIssueV1] = []

    def issue(
        code: str,
        severity: ValidationSeverity,
        field_path: str,
        message: str,
        resolution: str | None = None,
    ) -> None:
        issues.append(
            ValidationIssueV1(
                code=code,
                severity=severity,
                field_path=field_path,
                message=message,
                suggested_resolution=resolution,
            )
        )

    _validate_profiles(definition, issue)
    _validate_local_keys(definition, issue)
    _validate_references(definition, issue)
    _validate_action_economy(definition, issue)
    _validate_resource_costs(definition, issue)
    _validate_mechanics(definition, issue)
    _validate_rules_text(definition, validation_mode, issue)

    status = (
        ValidationStatus.invalid
        if any(item.severity is ValidationSeverity.error for item in issues)
        else ValidationStatus.warnings
        if issues
        else ValidationStatus.valid
    )
    return ValidationReceiptV1(
        status=status,
        mode=validation_mode,
        validator_version=VALIDATOR_VERSION,
        canonicalizer_version=CANONICALIZER_VERSION,
        issues=issues,
        definition_digest=compute_definition_digest(definition),
        validated_at=validated_at,
    )


def _validate_profiles(definition: StatblockDefinitionV1, issue: IssueEmitter) -> None:
    defaults = sum(profile.default for profile in definition.defenses.armor_classes)
    if defaults != 1:
        issue(
            "DEFAULT_ARMOR_CLASS_CARDINALITY",
            ValidationSeverity.error,
            "defenses.armor_classes",
            "Exactly one armor-class profile must be marked default.",
        )

    hp = definition.vitality.hit_points
    if hp.method == "formula" and (hp.formula is None or hp.fixed_value is not None):
        issue(
            "HP_METHOD_FIELDS_INCOHERENT",
            ValidationSeverity.error,
            "vitality.hit_points",
            "Formula HP requires formula and must not include fixed_value.",
        )
    if hp.method == "fixed" and (hp.fixed_value is None or hp.formula is not None):
        issue(
            "HP_METHOD_FIELDS_INCOHERENT",
            ValidationSeverity.error,
            "vitality.hit_points",
            "Fixed HP requires fixed_value and must not include formula.",
        )
    if hp.formula and hp.displayed_average is not None:
        average = hp.formula.count * (hp.formula.die + 1) // 2 + hp.formula.modifier
        if hp.displayed_average != average:
            issue(
                "HP_DISPLAYED_AVERAGE_MISMATCH",
                ValidationSeverity.error,
                "vitality.hit_points.displayed_average",
                "Displayed HP average does not match the typed dice formula.",
            )

    challenge = definition.challenge
    expected_bonus = _CR_PROFICIENCY_BONUS.get(challenge.rating)
    if expected_bonus is None:
        issue(
            "RULESET_CR_INVALID",
            ValidationSeverity.error,
            "challenge.rating",
            "Challenge rating is not a canonical D&D 5e CR value.",
        )
    elif challenge.proficiency_bonus != expected_bonus:
        issue(
            "RULESET_CR_PROFICIENCY_MISMATCH",
            ValidationSeverity.error,
            "challenge.proficiency_bonus",
            "Challenge proficiency bonus does not match the selected CR.",
        )

    wisdom_mod = (definition.abilities.wisdom - 10) // 2
    perception = next(
        (
            skill
            for skill in definition.proficiencies.skills
            if skill.skill.casefold() == "perception"
        ),
        None,
    )
    if perception is not None:
        expected_passive = 10 + perception.value
        if definition.senses.passive_perception != expected_passive:
            issue(
                "PASSIVE_PERCEPTION_MISMATCH",
                ValidationSeverity.error,
                "senses.passive_perception",
                "Passive Perception must equal 10 + Perception skill value.",
            )
    else:
        expected_passive = 10 + wisdom_mod
        if definition.senses.passive_perception != expected_passive:
            issue(
                "PASSIVE_PERCEPTION_UNVERIFIED",
                ValidationSeverity.warning,
                "senses.passive_perception",
                "Passive Perception differs from Wisdom without a typed Perception skill.",
                "Add a Perception skill or confirm the value during review.",
            )


def _validate_local_keys(definition: StatblockDefinitionV1, issue: IssueEmitter) -> None:
    groups = (
        ("defenses.armor_classes", [item.key for item in definition.defenses.armor_classes]),
        ("defenses.damage_interactions", [item.key for item in definition.defenses.damage_interactions]),
        ("movement.modes", [item.key for item in definition.movement.modes]),
        ("resources", [item.key for item in definition.resources]),
        ("rule_elements", [item.key for item in definition.rule_elements]),
        ("phases", [item.key for item in definition.phases]),
    )
    for field_path, keys in groups:
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        for key in duplicates:
            issue(
                "DUPLICATE_LOCAL_KEY",
                ValidationSeverity.error,
                field_path,
                f"Local key '{key}' is duplicated.",
            )
    defaults = sum(phase.default for phase in definition.phases)
    if definition.phases and defaults != 1:
        issue(
            "DEFAULT_PHASE_CARDINALITY",
            ValidationSeverity.error,
            "phases",
            "A phased creature must have exactly one default phase.",
        )


def _validate_references(definition: StatblockDefinitionV1, issue: IssueEmitter) -> None:
    element_keys = {item.key for item in definition.rule_elements}
    resource_keys = {item.key for item in definition.resources}
    phase_keys = {phase.key for phase in definition.phases}
    movement_keys = {mode.key for mode in definition.movement.modes}

    for index, element in enumerate(definition.rule_elements):
        path = f"rule_elements[{index}]"
        if element.activation.trigger and element.activation.trigger.source_element_key:
            _require_reference(
                element.activation.trigger.source_element_key,
                element_keys,
                issue,
                "UNKNOWN_ELEMENT_REFERENCE",
                f"{path}.activation.trigger.source_element_key",
            )
        if element.usage.resource_key:
            _require_reference(
                element.usage.resource_key,
                resource_keys,
                issue,
                "UNKNOWN_RESOURCE_REFERENCE",
                f"{path}.usage.resource_key",
            )
        for cost_index, cost in enumerate(element.costs):
            _require_reference(
                cost.resource_key,
                resource_keys,
                issue,
                "UNKNOWN_RESOURCE_REFERENCE",
                f"{path}.costs[{cost_index}].resource_key",
            )

        mechanic = element.mechanic
        if isinstance(mechanic, MultiattackMechanic):
            for sequence_index, sequence in enumerate(mechanic.sequences):
                target_path = f"{path}.mechanic.sequences[{sequence_index}].element_key"
                _require_reference(
                    sequence.element_key,
                    element_keys,
                    issue,
                    "UNKNOWN_MULTIATTACK_ELEMENT",
                    target_path,
                )
                if sequence.element_key == element.key:
                    issue(
                        "FORBIDDEN_REFERENCE_CYCLE",
                        ValidationSeverity.error,
                        target_path,
                        "A multiattack cannot reference itself.",
                    )
                referenced = next(
                    (item for item in definition.rule_elements if item.key == sequence.element_key),
                    None,
                )
                if referenced and isinstance(referenced.mechanic, MultiattackMechanic):
                    issue(
                        "FORBIDDEN_REFERENCE_CYCLE",
                        ValidationSeverity.error,
                        target_path,
                        "A multiattack cannot sequence another multiattack.",
                    )
        if isinstance(mechanic, PhaseTransitionMechanic):
            _require_reference(
                mechanic.destination_phase_key,
                phase_keys,
                issue,
                "UNKNOWN_PHASE_REFERENCE",
                f"{path}.mechanic.destination_phase_key",
            )
        if isinstance(mechanic, SpellcastingMechanic):
            for group_index, group in enumerate(mechanic.groups):
                if group.usage.resource_key:
                    _require_reference(
                        group.usage.resource_key,
                        resource_keys,
                        issue,
                        "UNKNOWN_RESOURCE_REFERENCE",
                        f"{path}.mechanic.groups[{group_index}].usage.resource_key",
                    )
        for effect_path, effect in _iter_element_effects(element):
            full_effect_path = f"{path}.{effect_path}"
            if isinstance(effect, (EnableElementsEffect, DisableElementsEffect)):
                for key_index, key in enumerate(effect.element_keys):
                    _require_reference(
                        key,
                        element_keys,
                        issue,
                        "UNKNOWN_ELEMENT_REFERENCE",
                        f"{full_effect_path}.element_keys[{key_index}]",
                    )
            elif isinstance(effect, EnterPhaseEffect):
                _require_reference(
                    effect.phase_key,
                    phase_keys,
                    issue,
                    "UNKNOWN_PHASE_REFERENCE",
                    f"{full_effect_path}.phase_key",
                )
            elif isinstance(effect, ResourceChangeEffect):
                _require_reference(
                    effect.resource_key,
                    resource_keys,
                    issue,
                    "UNKNOWN_RESOURCE_REFERENCE",
                    f"{full_effect_path}.resource_key",
                )
            elif isinstance(effect, MovementEffect) and effect.movement_mode_key:
                _require_reference(
                    effect.movement_mode_key,
                    movement_keys,
                    issue,
                    "UNKNOWN_MOVEMENT_REFERENCE",
                    f"{full_effect_path}.movement_mode_key",
                )

    for phase_index, phase in enumerate(definition.phases):
        enabled = set(phase.enabled_element_keys)
        disabled = set(phase.disabled_element_keys)
        for key in phase.enabled_element_keys:
            _require_reference(
                key,
                element_keys,
                issue,
                "UNKNOWN_PHASE_ELEMENT",
                f"phases[{phase_index}].enabled_element_keys",
            )
        for key in phase.disabled_element_keys:
            _require_reference(
                key,
                element_keys,
                issue,
                "UNKNOWN_PHASE_ELEMENT",
                f"phases[{phase_index}].disabled_element_keys",
            )
        for key in sorted(enabled & disabled):
            issue(
                "PHASE_ELEMENT_SET_CONFLICT",
                ValidationSeverity.error,
                f"phases[{phase_index}]",
                f"Element '{key}' cannot be both enabled and disabled.",
            )


def _validate_action_economy(
    definition: StatblockDefinitionV1, issue: IssueEmitter
) -> None:
    resource_keys = {resource.key for resource in definition.resources}
    for index, element in enumerate(definition.rule_elements):
        path = f"rule_elements[{index}]"
        if element.activation.kind not in _SECTION_ACTIVATIONS[element.section]:
            issue(
                "SECTION_ACTIVATION_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.activation.kind",
                f"Activation '{element.activation.kind.value}' is not valid for section '{element.section.value}'.",
            )
        if element.section is RuleSection.reaction and not (
            element.activation.trigger or element.activation.timing_text
        ):
            issue(
                "REACTION_TRIGGER_REQUIRED",
                ValidationSeverity.error,
                f"{path}.activation",
                "A reaction needs a trigger or timing expression.",
            )
        if element.section is RuleSection.legendary_action:
            if not element.costs or element.usage.kind is not UsageKind.resource:
                issue(
                    "LEGENDARY_RESOURCE_REQUIRED",
                    ValidationSeverity.error,
                    path,
                    "Legendary actions require resource usage and at least one cost.",
                )
            elif element.usage.resource_key is None:
                issue(
                    "LEGENDARY_RESOURCE_REQUIRED",
                    ValidationSeverity.error,
                    f"{path}.usage.resource_key",
                    "Legendary actions require usage.resource_key.",
                )
            elif element.usage.resource_key not in resource_keys:
                issue(
                    "LEGENDARY_RESOURCE_REQUIRED",
                    ValidationSeverity.error,
                    f"{path}.usage.resource_key",
                    "Legendary usage.resource_key must point to an existing resource pool.",
                )
            elif any(
                cost.resource_key != element.usage.resource_key for cost in element.costs
            ):
                issue(
                    "LEGENDARY_RESOURCE_MISMATCH",
                    ValidationSeverity.error,
                    f"{path}.costs",
                    "Legendary usage.resource_key must match every cost.resource_key.",
                )
            elif not any(cost.resource_key in resource_keys for cost in element.costs):
                issue(
                    "LEGENDARY_RESOURCE_REQUIRED",
                    ValidationSeverity.error,
                    f"{path}.costs",
                    "Legendary action costs must point to an existing resource pool.",
                )
        if element.section is RuleSection.lair_action:
            if definition.lair is None:
                issue(
                    "LAIR_CONTEXT_REQUIRED",
                    ValidationSeverity.error,
                    path,
                    "A lair action requires a lair profile.",
                )
            if not element.activation.timing_text and not (
                definition.lair and definition.lair.initiative_count is not None
            ):
                issue(
                    "LAIR_TIMING_REQUIRED",
                    ValidationSeverity.error,
                    f"{path}.activation",
                    "A lair action requires an initiative timing expression.",
                )


def _validate_resource_costs(
    definition: StatblockDefinitionV1, issue: IssueEmitter
) -> None:
    """Ensure each element's costs are affordable against typed pool maxima."""

    pools = {pool.key: pool for pool in definition.resources}
    for index, element in enumerate(definition.rule_elements):
        path = f"rule_elements[{index}]"
        seen_keys: dict[str, int] = {}
        running_totals: dict[str, int] = {}
        for cost_index, cost in enumerate(element.costs):
            pool = pools.get(cost.resource_key)
            if pool is None:
                continue
            cost_path = f"{path}.costs[{cost_index}]"
            if cost.resource_key in seen_keys:
                issue(
                    "RESOURCE_COST_DUPLICATE_POOL",
                    ValidationSeverity.error,
                    f"{cost_path}.resource_key",
                    f"Resource pool '{cost.resource_key}' appears more than once in costs; "
                    "use a single cost entry.",
                )
            else:
                seen_keys[cost.resource_key] = cost_index

            if cost.amount > pool.maximum:
                issue(
                    "RESOURCE_COST_EXCEEDS_POOL",
                    ValidationSeverity.error,
                    f"{cost_path}.amount",
                    f"Cost amount {cost.amount} exceeds pool '{cost.resource_key}' "
                    f"maximum of {pool.maximum}.",
                )

            running_totals[cost.resource_key] = (
                running_totals.get(cost.resource_key, 0) + cost.amount
            )
            total = running_totals[cost.resource_key]
            # Aggregate overflow when no single entry alone exceeds the maximum.
            if total > pool.maximum and cost.amount <= pool.maximum:
                issue(
                    "RESOURCE_COST_EXCEEDS_POOL",
                    ValidationSeverity.error,
                    f"{cost_path}.amount",
                    f"Combined costs for pool '{cost.resource_key}' ({total}) exceed "
                    f"maximum of {pool.maximum}.",
                )


def _validate_mechanics(definition: StatblockDefinitionV1, issue: IssueEmitter) -> None:
    for index, element in enumerate(definition.rule_elements):
        path = f"rule_elements[{index}]"
        mechanic = element.mechanic
        _validate_usage(
            element.usage, f"{path}.usage", issue, allow_spell_slots=False
        )
        if isinstance(mechanic, AttackMechanic):
            _validate_attack_mechanic(mechanic, f"{path}.mechanic", issue)
        if isinstance(mechanic, SpellcastingMechanic):
            _validate_spellcasting_mechanic(mechanic, f"{path}.mechanic", issue)
        if isinstance(mechanic, HumanAdjudicatedMechanic) and (
            element.automation_support is not AutomationSupport.manual
        ):
            issue(
                "HUMAN_ADJUDICATED_AUTOMATION_MISMATCH",
                ValidationSeverity.error,
                f"{path}.automation_support",
                "Human-adjudicated mechanics must declare manual automation support.",
            )


def _validate_usage(
    usage: Usage,
    path: str,
    issue: IssueEmitter,
    *,
    allow_spell_slots: bool = False,
) -> None:
    kind = usage.kind
    if kind is UsageKind.recharge:
        if usage.recharge_range is None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.recharge_range",
                "Recharge usage requires an ordered d6 recharge_range.",
            )
        elif usage.recharge_range.minimum > usage.recharge_range.maximum:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.recharge_range",
                "Recharge minimum must be less than or equal to maximum.",
            )
        if usage.uses is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                "Recharge usage must not set uses.",
            )
        if usage.resource_key is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                "Recharge usage must not set resource_key.",
            )
        return

    if usage.recharge_range is not None:
        issue(
            "USAGE_FIELDS_INCOHERENT",
            ValidationSeverity.error,
            f"{path}.recharge_range",
            "Only recharge usage may include recharge_range.",
        )

    if kind is UsageKind.at_will:
        if usage.uses is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                "At-will usage must not set uses.",
            )
        if usage.resource_key is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                "At-will usage must not set resource_key.",
            )
        return

    if kind is UsageKind.spell_slots:
        if not allow_spell_slots:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.kind",
                "spell_slots usage is reserved for leveled prepared/known spell groups.",
            )
            return
        if usage.uses is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                "Spell-slot usage must not set uses; encode slot count on SpellGroup.slots.",
            )
        if usage.resource_key is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                "Spell-slot usage must not set resource_key.",
            )
        return

    if kind in _LIMITED_USE_KINDS:
        if usage.uses is None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                f"{kind.value} usage requires uses.",
            )
        if usage.resource_key is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                f"{kind.value} usage must not set resource_key.",
            )
        return

    if kind is UsageKind.once:
        if usage.uses is not None and usage.uses != 1:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                "Once usage may omit uses or set uses to 1.",
            )
        if usage.resource_key is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                "Once usage must not set resource_key.",
            )
        return

    if kind is UsageKind.resource:
        if usage.resource_key is None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.resource_key",
                "Resource usage requires resource_key.",
            )
        if usage.uses is not None:
            issue(
                "USAGE_FIELDS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.uses",
                "Resource usage must not set uses.",
            )
        return

    # manual: recharge already rejected; uses/resource_key optional for GM text.


def _validate_attack_mechanic(
    mechanic: AttackMechanic, path: str, issue: IssueEmitter
) -> None:
    is_melee = mechanic.attack_type in {AttackType.melee_weapon, AttackType.melee_spell}
    is_ranged = mechanic.attack_type in {
        AttackType.ranged_weapon,
        AttackType.ranged_spell,
    }
    if is_melee:
        if mechanic.reach is None:
            issue(
                "ATTACK_REACH_REQUIRED",
                ValidationSeverity.error,
                f"{path}.reach",
                "A melee attack requires typed reach.",
            )
        if mechanic.range is not None:
            issue(
                "ATTACK_RANGE_UNEXPECTED",
                ValidationSeverity.error,
                f"{path}.range",
                "A melee attack must not include typed range.",
            )
    if is_ranged:
        if mechanic.range is None:
            issue(
                "ATTACK_RANGE_REQUIRED",
                ValidationSeverity.error,
                f"{path}.range",
                "A ranged attack requires typed range.",
            )
        if mechanic.reach is not None:
            issue(
                "ATTACK_REACH_UNEXPECTED",
                ValidationSeverity.error,
                f"{path}.reach",
                "A ranged attack must not include typed reach.",
            )
    if mechanic.range is not None and mechanic.range.long is not None:
        if (
            mechanic.range.long.unit != mechanic.range.normal.unit
            or mechanic.range.long.value < mechanic.range.normal.value
        ):
            issue(
                "ATTACK_RANGE_ORDER_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.range",
                "Attack long range must use the same unit and be >= normal range.",
            )

    target = mechanic.target
    target_path = f"{path}.target"
    # Attack distance authority lives on AttackMechanic.reach / .range only.
    if target.range is not None:
        issue(
            "ATTACK_TARGET_RANGE_UNEXPECTED",
            ValidationSeverity.error,
            f"{target_path}.range",
            "Attack target must not set range; use mechanic.reach or mechanic.range.",
        )
    if target.kind is TargetKind.creatures and target.count is None:
        issue(
            "ATTACK_TARGET_COUNT_REQUIRED",
            ValidationSeverity.error,
            f"{target_path}.count",
            "A creatures target requires count.",
        )
    if target.kind is TargetKind.creature and target.count not in (None, 1):
        issue(
            "ATTACK_TARGET_COUNT_INCOHERENT",
            ValidationSeverity.error,
            f"{target_path}.count",
            "A single creature target must omit count or set it to 1.",
        )
    if target.kind is TargetKind.self and target.count is not None:
        issue(
            "ATTACK_TARGET_COUNT_INCOHERENT",
            ValidationSeverity.error,
            f"{target_path}.count",
            "A self target must not set count.",
        )
    if target.kind is TargetKind.area:
        if not target.area:
            issue(
                "ATTACK_TARGET_AREA_REQUIRED",
                ValidationSeverity.error,
                f"{target_path}.area",
                "An area target requires area.",
            )
    elif target.area is not None:
        issue(
            "ATTACK_TARGET_AREA_UNEXPECTED",
            ValidationSeverity.error,
            f"{target_path}.area",
            "Only an area target may set area.",
        )


def _validate_spellcasting_mechanic(
    mechanic: SpellcastingMechanic, path: str, issue: IssueEmitter
) -> None:
    mode = mechanic.casting_mode
    if mode in {CastingMode.prepared, CastingMode.known}:
        if mechanic.caster_level is None:
            issue(
                "SPELLCASTING_MODE_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.caster_level",
                f"{mode.value} spellcasting requires caster_level.",
            )
        if mechanic.ability is None:
            issue(
                "SPELLCASTING_MODE_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.ability",
                f"{mode.value} spellcasting requires ability.",
            )
    if mode is CastingMode.charges and mechanic.ability is None:
        issue(
            "SPELLCASTING_MODE_INCOHERENT",
            ValidationSeverity.error,
            f"{path}.ability",
            "Charges spellcasting requires ability.",
        )

    for group_index, group in enumerate(mechanic.groups):
        group_path = f"{path}.groups[{group_index}]"
        allow_spell_slots = (
            mode in {CastingMode.prepared, CastingMode.known}
            and group.level is not None
            and group.level > 0
        )
        _validate_usage(
            group.usage,
            f"{group_path}.usage",
            issue,
            allow_spell_slots=allow_spell_slots,
        )
        _validate_spell_group(group, mode, group_path, issue)


def _validate_spell_group(
    group: SpellGroup,
    mode: CastingMode,
    path: str,
    issue: IssueEmitter,
) -> None:
    if mode is CastingMode.innate:
        if group.slots is not None:
            issue(
                "SPELL_GROUP_SLOTS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.slots",
                "Innate spell groups must not use slots; encode limited uses on usage.",
            )
        if group.level is not None and not (0 <= group.level <= 9):
            issue(
                "SPELL_GROUP_LEVEL_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.level",
                "Spell group level must be between 0 and 9.",
            )
        return

    if mode in {CastingMode.prepared, CastingMode.known}:
        if group.level is None:
            issue(
                "SPELL_GROUP_LEVEL_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.level",
                f"{mode.value} spell groups require level.",
            )
            return
        if group.level == 0:
            if group.slots is not None:
                issue(
                    "SPELL_GROUP_SLOTS_INCOHERENT",
                    ValidationSeverity.error,
                    f"{path}.slots",
                    "Cantrip groups must not set slots.",
                )
            if group.usage.kind is not UsageKind.at_will:
                issue(
                    "SPELL_GROUP_USAGE_INCOHERENT",
                    ValidationSeverity.error,
                    f"{path}.usage.kind",
                    "Cantrip groups must use at_will usage.",
                )
        else:
            if group.slots is None:
                issue(
                    "SPELL_GROUP_SLOTS_INCOHERENT",
                    ValidationSeverity.error,
                    f"{path}.slots",
                    "Leveled prepared/known groups require slots.",
                )
            if group.usage.kind is not UsageKind.spell_slots:
                issue(
                    "SPELL_GROUP_USAGE_INCOHERENT",
                    ValidationSeverity.error,
                    f"{path}.usage.kind",
                    "Leveled prepared/known groups must use spell_slots usage with slots.",
                )
        return

    if mode is CastingMode.charges:
        if group.usage.kind is not UsageKind.resource:
            issue(
                "SPELL_GROUP_USAGE_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.usage.kind",
                "Charges spell groups require resource usage.",
            )
        if group.slots is not None:
            issue(
                "SPELL_GROUP_SLOTS_INCOHERENT",
                ValidationSeverity.error,
                f"{path}.slots",
                "Charges spell groups must not use slots.",
            )


def _validate_rules_text(
    definition: StatblockDefinitionV1, mode: ValidationMode, issue: IssueEmitter
) -> None:
    severity = (
        ValidationSeverity.error
        if mode is ValidationMode.persistence
        else ValidationSeverity.warning
    )
    for index, element in enumerate(definition.rule_elements):
        path = f"rule_elements[{index}]"
        mechanic = element.mechanic
        if isinstance(mechanic, AttackMechanic):
            match = _ATTACK_BONUS.search(element.rules_text)
            if match and int(match.group(1)) != mechanic.attack_bonus:
                issue(
                    "RULES_TEXT_ATTACK_BONUS_MISMATCH",
                    severity,
                    f"{path}.rules_text",
                    "Rules text attack bonus conflicts with typed attack_bonus.",
                )
            typed_damage = next(
                (effect for effect in mechanic.hit_effects if isinstance(effect, DamageEffect)),
                None,
            )
            parsed_damage = _DAMAGE_CLAUSE.search(element.rules_text)
            if typed_damage and parsed_damage:
                modifier = int(parsed_damage.group(4) or 0)
                if parsed_damage.group(3) == "-":
                    modifier = -modifier
                text_dice = (int(parsed_damage.group(1)), int(parsed_damage.group(2)), modifier)
                typed_dice = (
                    typed_damage.damage.count,
                    typed_damage.damage.die,
                    typed_damage.damage.modifier,
                )
                if (
                    text_dice != typed_dice
                    or parsed_damage.group(5).casefold() != typed_damage.damage_type.casefold()
                ):
                    issue(
                        "RULES_TEXT_DAMAGE_MISMATCH",
                        severity,
                        f"{path}.rules_text",
                        "Rules text damage conflicts with the first typed hit damage effect.",
                    )
        if isinstance(mechanic, SaveEffectMechanic):
            match = _SAVE_DC.search(element.rules_text)
            if match and int(match.group(1)) != mechanic.save.dc:
                issue(
                    "RULES_TEXT_SAVE_DC_MISMATCH",
                    severity,
                    f"{path}.rules_text",
                    "Rules text save DC conflicts with typed save DC.",
                )
        if element.section is RuleSection.reaction and re.search(
            r"\bas an action\b", element.rules_text, re.IGNORECASE
        ):
            issue(
                "RULES_TEXT_SECTION_MISMATCH",
                severity,
                f"{path}.rules_text",
                "Reaction rules text unambiguously says it is used as an action.",
            )


def _require_reference(
    key: str, keys: set[str], issue: IssueEmitter, code: str, field_path: str
) -> None:
    if key not in keys:
        issue(code, ValidationSeverity.error, field_path, f"Unknown local reference '{key}'.")


def _iter_element_effects(element: RuleElement) -> Iterable[tuple[str, object]]:
    """Yield ``(relative_field_path, effect)`` preserving collection identity."""

    mechanic = element.mechanic
    if isinstance(mechanic, AttackMechanic):
        for index, effect in enumerate(mechanic.hit_effects):
            yield f"mechanic.hit_effects[{index}]", effect
        for index, effect in enumerate(mechanic.miss_effects):
            yield f"mechanic.miss_effects[{index}]", effect
        return
    if isinstance(mechanic, SaveEffectMechanic):
        for index, effect in enumerate(mechanic.failure_effects):
            yield f"mechanic.failure_effects[{index}]", effect
        for index, effect in enumerate(mechanic.success_effects):
            yield f"mechanic.success_effects[{index}]", effect
        return
    if isinstance(mechanic, PhaseTransitionMechanic):
        for index, effect in enumerate(mechanic.effects):
            yield f"mechanic.effects[{index}]", effect
        return
    effects = getattr(mechanic, "effects", None)
    if isinstance(effects, list):
        for index, effect in enumerate(effects):
            yield f"mechanic.effects[{index}]", effect
