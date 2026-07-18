"""Rule elements and the top-level statblock definition."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import Field

from statblocks_v1.domain.primitives import (
    AbilityName,
    Activation,
    AutomationSupport,
    Distance,
    Effect,
    RangeProfile,
    ResourceCost,
    StrictModel,
    TargetProfile,
    Usage,
)
from statblocks_v1.domain.profiles import (
    AbilityScores,
    ChallengeProfile,
    CommunicationProfile,
    CreatureIdentity,
    CreaturePhase,
    DefenseProfile,
    LairProfile,
    MovementProfile,
    ProficiencyProfile,
    ResourcePool,
    RulesetRef,
    SenseProfile,
    StatblockFlavorText,
    VitalityProfile,
)


class RuleSection(str, Enum):
    trait = "trait"
    action = "action"
    bonus_action = "bonus_action"
    reaction = "reaction"
    legendary_action = "legendary_action"
    lair_action = "lair_action"
    regional_effect = "regional_effect"


class AttackType(str, Enum):
    melee_weapon = "melee_weapon"
    ranged_weapon = "ranged_weapon"
    melee_spell = "melee_spell"
    ranged_spell = "ranged_spell"
    special = "special"


class AttackMechanic(StrictModel):
    kind: Literal["attack"] = "attack"
    attack_type: AttackType
    attack_bonus: int
    reach: Distance | None = None
    range: RangeProfile | None = None
    target: TargetProfile
    hit_effects: list[Effect] = Field(default_factory=list)
    miss_effects: list[Effect] = Field(default_factory=list)


class SavingThrow(StrictModel):
    ability: AbilityName
    dc: int = Field(ge=1)


class SaveEffectMechanic(StrictModel):
    kind: Literal["save_effect"] = "save_effect"
    save: SavingThrow
    target: TargetProfile
    failure_effects: list[Effect] = Field(default_factory=list)
    success_effects: list[Effect] = Field(default_factory=list)


class ElementUse(StrictModel):
    element_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    count: int = Field(ge=1)
    choice_group: str | None = None


class MultiattackMechanic(StrictModel):
    kind: Literal["multiattack"] = "multiattack"
    sequences: list[ElementUse] = Field(min_length=1)


class SpellRef(StrictModel):
    name: str = Field(min_length=1)
    level: int | None = Field(default=None, ge=0, le=9)
    school: str | None = None
    source_id: str | None = None
    rules_text: str | None = None


class SpellGroup(StrictModel):
    usage: Usage
    level: int | None = Field(default=None, ge=0, le=9)
    slots: int | None = Field(default=None, ge=1)
    spells: list[SpellRef] = Field(min_length=1)


class CastingMode(str, Enum):
    prepared = "prepared"
    known = "known"
    innate = "innate"
    charges = "charges"
    special = "special"


class SpellcastingMechanic(StrictModel):
    kind: Literal["spellcasting"] = "spellcasting"
    casting_mode: CastingMode
    ability: AbilityName | None = None
    save_dc: int | None = Field(default=None, ge=1)
    attack_bonus: int | None = None
    caster_level: int | None = Field(default=None, ge=1)
    groups: list[SpellGroup] = Field(min_length=1)


class PassiveMechanic(StrictModel):
    kind: Literal["passive"] = "passive"
    effects: list[Effect] = Field(default_factory=list)


class CompositeMechanic(StrictModel):
    kind: Literal["composite"] = "composite"
    target: TargetProfile | None = None
    effects: list[Effect] = Field(default_factory=list)


class PhaseTransitionMechanic(StrictModel):
    kind: Literal["phase_transition"] = "phase_transition"
    destination_phase_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    effects: list[Effect] = Field(default_factory=list)


class HumanAdjudicatedMechanic(StrictModel):
    kind: Literal["human_adjudicated"] = "human_adjudicated"
    adjudication_tags: list[str] = Field(default_factory=list)


Mechanic = Annotated[
    Union[
        AttackMechanic,
        SaveEffectMechanic,
        MultiattackMechanic,
        SpellcastingMechanic,
        PassiveMechanic,
        CompositeMechanic,
        PhaseTransitionMechanic,
        HumanAdjudicatedMechanic,
    ],
    Field(discriminator="kind"),
]


class RuleElement(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    section: RuleSection
    summary: str | None = None
    rules_text: str = Field(min_length=1)
    activation: Activation
    usage: Usage
    costs: list[ResourceCost] = Field(default_factory=list)
    mechanic: Mechanic
    tags: list[str] = Field(default_factory=list)
    automation_support: AutomationSupport


class StatblockDefinitionV1(StrictModel):
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
    resources: list[ResourcePool] = Field(default_factory=list)
    rule_elements: list[RuleElement] = Field(min_length=1)
    phases: list[CreaturePhase] = Field(default_factory=list)
    lair: LairProfile | None = None
    flavor_text: StatblockFlavorText | None = None
