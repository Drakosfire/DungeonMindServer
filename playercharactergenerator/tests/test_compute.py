from playercharactergenerator.models.pcg_models import (
    AbilityScores,
    GenerationInput,
    ValidationChoices,
)
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.compute import compute_derived_stats
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def test_compute_fighter_l1_chain_mail_shield_defense_ac_and_hp() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="fighter",
        raceId="human",
        level=1,
        backgroundId="soldier",
        concept="A disciplined frontline soldier who protects allies.",
    )
    constraints = engine.get_constraints(input_data)

    # Post-racial (human has no bonuses in our v0 catalog)
    choices = ValidationChoices(
        abilityScores=AbilityScores(
            strength=15,
            dexterity=12,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=8,
        ),
        selectedSkills=["Athletics", "Intimidation", "Perception", "Survival"],  # 2 bg + 2 class
        equipmentPackageId="A",  # chain-mail + shield
        featureChoices={"fighter-fighting-style": "defense"},
    )

    ok, issues, derived, sections = compute_derived_stats(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )

    assert ok is True
    assert issues == []
    assert derived is not None

    # CON 14 => +2; level 1 fighter HP = 10 + 2
    assert derived.hit_points_max == 12

    # Chain mail (16) + shield (2) + Defense (+1) = 19
    assert derived.armor_class == 19

    # Proficiency bonus (levels 1-3) = +2
    assert derived.proficiency_bonus == 2

    # Initiative = DEX mod (12 => +1)
    assert derived.initiative == 1

    # Passive perception = 10 + (WIS mod 0 + prof 2) = 12
    assert derived.passive_perception == 12

    # Ensure we left debug sections in place (useful for diagnosing armor parsing)
    assert "compute" in sections


def test_compute_spell_slots_section_warlock_l3_pact_magic() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="warlock",
        raceId="human",
        level=3,
        backgroundId="sage",
        concept="An occult scholar who channels forbidden power through a pact.",
    )
    constraints = engine.get_constraints(input_data)

    choices = ValidationChoices(
        abilityScores=AbilityScores(
            strength=8,
            dexterity=14,
            constitution=14,
            intelligence=10,
            wisdom=10,
            charisma=15,
        ),
        selectedSkills=["Arcana", "History", "Deception", "Investigation"],
        equipmentPackageId="A",
        featureChoices={"warlock-patron": "fiend", "warlock-pact-boon": "tome"},
        selectedCantrips=["eldritch-blast", "mage-hand"],
        selectedSpells=["hex", "armor-of-agathys", "hellish-rebuke", "misty-step"],
    )

    ok, issues, _sections = validate_translated_choices(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert ok is True, {"issues": issues, "sections": _sections}

    ok2, issues2, derived, sections = compute_derived_stats(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert ok2 is True
    assert issues2 == []
    assert derived is not None

    assert "spellSlots" in sections
    assert sections["spellSlots"]["details"]["kind"] == "pact"
    assert sections["spellSlots"]["details"]["pactSlots"] == 2
    assert sections["spellSlots"]["details"]["pactSlotLevel"] == 2


