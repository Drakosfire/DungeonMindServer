from playercharactergenerator.models.pcg_models import AbilityScores, GenerationInput, ValidationChoices
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def test_spell_validation_wizard_l3_prepared_counts_and_membership() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="wizard",
        raceId="human",
        level=3,
        backgroundId="sage",
        concept="A curious scholar-mage who studies ancient ruins and prefers utility and defense.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None

    # INT 15 => mod +2; prepared (mod + level) => 5 spells, 3 cantrips
    choices = ValidationChoices(
        abilityScores=AbilityScores(
            strength=8,
            dexterity=13,
            constitution=14,
            intelligence=15,
            wisdom=12,
            charisma=10,
        ),
        selectedSkills=["Arcana", "History", "Insight", "Investigation"],  # bg + class
        equipmentPackageId="A",
        featureChoices={"wizard-subclass": "evocation"},
        selectedCantrips=["fire-bolt", "mage-hand", "prestidigitation"],
        selectedSpells=["magic-missile", "shield", "burning-hands", "mirror-image", "misty-step"],
    )

    ok, issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert ok is True, {"issues": issues, "sections": sections}
    assert issues == []
    assert sections["spells"]["success"] is True


def test_spell_validation_rejects_invalid_spell_id() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="cleric",
        raceId="dwarf",
        level=1,
        backgroundId="acolyte",
        concept="A devout healer who protects the faithful and mends wounds.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None

    # WIS 16 => mod +3; prepared => 4 spells, 3 cantrips (level 1)
    choices = ValidationChoices(
        abilityScores=AbilityScores(
            strength=13,
            dexterity=10,
            constitution=16,  # dwarf +2 in our catalog (post-racial), ok for other validators
            intelligence=10,
            wisdom=16,
            charisma=8,
        ),
        selectedSkills=["Insight", "Religion", "History", "Persuasion"],  # 2 bg + 2 class-ish (not perfect but allowed set in constraints)
        equipmentPackageId="A",
        featureChoices={"cleric-subclass": "life"},
        selectedCantrips=["light", "sacred-flame", "thaumaturgy"],
        selectedSpells=["cure-wounds", "healing-word", "guiding-bolt", "not-a-real-spell"],
    )

    ok, issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert ok is False
    assert any("Spell not allowed by constraints" in i for i in issues)
    assert sections["spells"]["success"] is False


