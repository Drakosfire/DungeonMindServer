"""Bounded primitive values used by the statblock v1 contract."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Canonical models reject unknown fields at every nesting level."""

    model_config = ConfigDict(extra="forbid")


class AbilityName(str, Enum):
    strength = "strength"
    dexterity = "dexterity"
    constitution = "constitution"
    intelligence = "intelligence"
    wisdom = "wisdom"
    charisma = "charisma"


class DistanceUnit(str, Enum):
    feet = "feet"


class DiceExpression(StrictModel):
    count: int = Field(ge=1)
    die: int = Field(ge=2)
    modifier: int = 0


class Distance(StrictModel):
    value: int = Field(ge=0)
    unit: DistanceUnit = DistanceUnit.feet


class RangeProfile(StrictModel):
    normal: Distance
    long: Distance | None = None


class TargetKind(str, Enum):
    creature = "creature"
    creatures = "creatures"
    self = "self"
    point = "point"
    area = "area"
    object = "object"
    structure = "structure"
    special = "special"


class TargetProfile(StrictModel):
    kind: TargetKind
    count: int | None = Field(default=None, ge=1)
    range: RangeProfile | None = None
    area: str | None = None
    qualifiers: list[str] = Field(default_factory=list)


class DurationKind(str, Enum):
    instantaneous = "instantaneous"
    until_start_turn = "until_start_turn"
    until_end_turn = "until_end_turn"
    rounds = "rounds"
    minutes = "minutes"
    hours = "hours"
    until_save = "until_save"
    permanent = "permanent"
    special = "special"


class Duration(StrictModel):
    kind: DurationKind
    value: int | None = Field(default=None, ge=1)


class Trigger(StrictModel):
    kind: str = Field(min_length=1)
    source_element_key: str | None = Field(
        default=None, pattern=r"^[a-z][a-z0-9_]*$"
    )
    condition_text: str | None = None


class ActivationKind(str, Enum):
    passive = "passive"
    action = "action"
    bonus_action = "bonus_action"
    reaction = "reaction"
    triggered = "triggered"
    legendary = "legendary"
    lair_initiative = "lair_initiative"
    special = "special"


class Activation(StrictModel):
    kind: ActivationKind
    trigger: Trigger | None = None
    timing_text: str | None = None


class UsageKind(str, Enum):
    at_will = "at_will"
    recharge = "recharge"
    per_turn = "per_turn"
    per_round = "per_round"
    per_day = "per_day"
    once = "once"
    resource = "resource"
    manual = "manual"


class Usage(StrictModel):
    kind: UsageKind
    recharge_range: tuple[int, int] | None = None
    uses: int | None = Field(default=None, ge=1)
    resource_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    refresh_text: str | None = None


class ResourceCost(StrictModel):
    resource_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    amount: int = Field(ge=1)


class AutomationSupport(str, Enum):
    full = "full"
    partial = "partial"
    manual = "manual"


class DamageEffect(StrictModel):
    kind: Literal["damage"] = "damage"
    damage: DiceExpression
    damage_type: str = Field(min_length=1)
    duration: Duration | None = None


class HealingEffect(StrictModel):
    kind: Literal["healing"] = "healing"
    healing: DiceExpression


class ConditionEffect(StrictModel):
    kind: Literal["condition"] = "condition"
    condition: str = Field(min_length=1)
    duration: Duration | None = None


class MovementEffect(StrictModel):
    kind: Literal["movement"] = "movement"
    movement_mode_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*$")
    distance: Distance | None = None


class ForcedMovementEffect(StrictModel):
    kind: Literal["forced_movement"] = "forced_movement"
    distance: Distance
    direction: str = Field(min_length=1)


class ResourceChangeEffect(StrictModel):
    kind: Literal["resource_change"] = "resource_change"
    resource_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    amount: int


class SummonEffect(StrictModel):
    kind: Literal["summon"] = "summon"
    creature_description: str = Field(min_length=1)
    duration: Duration | None = None


class StatModifierEffect(StrictModel):
    kind: Literal["stat_modifier"] = "stat_modifier"
    stat: str = Field(min_length=1)
    modifier: int
    duration: Duration | None = None


class EnableElementsEffect(StrictModel):
    kind: Literal["enable_elements"] = "enable_elements"
    element_keys: list[str] = Field(min_length=1)


class DisableElementsEffect(StrictModel):
    kind: Literal["disable_elements"] = "disable_elements"
    element_keys: list[str] = Field(min_length=1)


class EnterPhaseEffect(StrictModel):
    kind: Literal["enter_phase"] = "enter_phase"
    phase_key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")


class HumanAdjudicatedEffect(StrictModel):
    kind: Literal["human_adjudicated"] = "human_adjudicated"
    adjudication_text: str = Field(min_length=1)


Effect = Annotated[
    Union[
        DamageEffect,
        HealingEffect,
        ConditionEffect,
        MovementEffect,
        ForcedMovementEffect,
        ResourceChangeEffect,
        SummonEffect,
        StatModifierEffect,
        EnableElementsEffect,
        DisableElementsEffect,
        EnterPhaseEffect,
        HumanAdjudicatedEffect,
    ],
    Field(discriminator="kind"),
]
