"""Creature profile models for the statblock v1 definition."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from statblocks_v1.domain.primitives import AbilityName, DiceExpression, Distance, StrictModel


class RulesetSystem(str, Enum):
    dnd5e = "dnd5e"


class RulesetEdition(str, Enum):
    edition_2014 = "2014"
    edition_2024 = "2024"


class RulesetRef(StrictModel):
    system: RulesetSystem
    edition: RulesetEdition
    house_ruleset_id: str | None = None


class CreatureIdentity(StrictModel):
    name: str = Field(min_length=1)
    size: str = Field(min_length=1)
    creature_type: str = Field(min_length=1)
    subtypes: list[str] = Field(default_factory=list)
    alignment: str | None = None


class ArmorClassProfile(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    value: int = Field(ge=0)
    label: str | None = None
    condition: str | None = None
    default: bool = Field(
        description="Exactly one profile in defenses.armor_classes must set true; all others false."
    )


class DamageInteractionKind(str, Enum):
    vulnerability = "vulnerability"
    resistance = "resistance"
    immunity = "immunity"


class DamageInteraction(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: DamageInteractionKind
    damage_types: list[str] = Field(min_length=1)
    qualifiers: list[str] = Field(default_factory=list)
    bypasses: list[str] = Field(default_factory=list)


class DefenseProfile(StrictModel):
    armor_classes: list[ArmorClassProfile] = Field(min_length=1)
    damage_interactions: list[DamageInteraction] = Field(default_factory=list)
    condition_immunities: list[str] = Field(default_factory=list)


class HitPointProfile(StrictModel):
    method: Literal["formula", "fixed"] = Field(
        description=(
            "'formula' sets formula and leaves fixed_value null; "
            "'fixed' sets fixed_value and leaves formula null."
        )
    )
    formula: DiceExpression | None = None
    fixed_value: int | None = Field(default=None, ge=1)
    displayed_average: int | None = Field(
        default=None,
        ge=1,
        description="When set, must equal the average of the typed formula.",
    )

    @model_validator(mode="after")
    def method_has_matching_value(self) -> "HitPointProfile":
        if self.method == "formula" and self.formula is None:
            raise ValueError("formula HP requires formula")
        if self.method == "fixed" and self.fixed_value is None:
            raise ValueError("fixed HP requires fixed_value")
        return self


class VitalityProfile(StrictModel):
    hit_points: HitPointProfile


class MovementModeKind(str, Enum):
    walk = "walk"
    fly = "fly"
    swim = "swim"
    climb = "climb"
    burrow = "burrow"
    hover = "hover"
    special = "special"


class MovementMode(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    mode: MovementModeKind
    distance: Distance
    qualifiers: list[str] = Field(default_factory=list)


class MovementProfile(StrictModel):
    modes: list[MovementMode] = Field(min_length=1)


class AbilityScores(StrictModel):
    strength: int = Field(ge=1, le=30)
    dexterity: int = Field(ge=1, le=30)
    constitution: int = Field(ge=1, le=30)
    intelligence: int = Field(ge=1, le=30)
    wisdom: int = Field(ge=1, le=30)
    charisma: int = Field(ge=1, le=30)


class ProficiencyDerivation(str, Enum):
    standard = "standard"
    expertise = "expertise"
    explicit_override = "explicit_override"


class SavingThrowBonus(StrictModel):
    ability: AbilityName
    value: int
    derivation: ProficiencyDerivation = Field(
        description=(
            "'standard' means value equals ability modifier plus proficiency bonus; "
            "'expertise' adds proficiency twice; use 'explicit_override' for any other value."
        )
    )
    note: str | None = None


class SkillBonus(StrictModel):
    """Authored skill bonus with explicit ability authority for derivation checks."""

    skill: str = Field(min_length=1)
    ability: AbilityName
    value: int
    derivation: ProficiencyDerivation = Field(
        description=(
            "'standard' means value equals ability modifier plus proficiency bonus; "
            "'expertise' adds proficiency twice; use 'explicit_override' for any other value."
        )
    )
    note: str | None = None


class ProficiencyProfile(StrictModel):
    """Authored save/skill bonuses. Proficiency bonus is authored only on challenge."""

    saving_throws: list[SavingThrowBonus] = Field(default_factory=list)
    skills: list[SkillBonus] = Field(default_factory=list)


class SenseKind(str, Enum):
    darkvision = "darkvision"
    blindsight = "blindsight"
    tremorsense = "tremorsense"
    truesight = "truesight"
    special = "special"


class Sense(StrictModel):
    kind: SenseKind
    range: Distance
    qualifiers: list[str] = Field(default_factory=list)


class SenseProfile(StrictModel):
    senses: list[Sense] = Field(default_factory=list)
    passive_perception: int = Field(
        ge=1,
        description=(
            "Must equal 10 + the Perception skill value when proficiencies.skills "
            "contains a Perception entry."
        ),
    )


class CommunicationProfile(StrictModel):
    languages: list[str] = Field(default_factory=list)
    telepathy_range: Distance | None = None
    special_modes: list[str] = Field(default_factory=list)


class ChallengeProfile(StrictModel):
    rating: str = Field(min_length=1)
    proficiency_bonus: int = Field(
        ge=0,
        description="Must match rating on the standard 5e challenge-rating table.",
    )
    xp_override: int | None = Field(default=None, ge=0)


class ResourcePool(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    maximum: int = Field(ge=1)
    refresh: str = Field(min_length=1)
    rules_text: str | None = None


class CreaturePhase(StrictModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    default: bool = Field(
        description="Exactly one phase must set true whenever phases are present."
    )
    enabled_element_keys: list[str] = Field(default_factory=list)
    disabled_element_keys: list[str] = Field(default_factory=list)
    entry_rules_text: str | None = None


class LairProfile(StrictModel):
    name: str | None = None
    description: str | None = None
    initiative_count: int | None = Field(default=None, ge=1, le=30)
    initiative_tiebreak: int | None = None
    regional_rules_text: str | None = None


class StatblockFlavorText(StrictModel):
    summary: str | None = None
    description: str | None = None
