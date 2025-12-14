from playercharactergenerator.models.pcg_models import AbilityScores, GenerationInput, ValidationChoices
from playercharactergenerator.rule_engine.pcg_rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def test_spell_validation_warlock_l3_pact_magic_counts_and_membership() -> None:
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="warlock",
        raceId="human",
        level=3,
        backgroundId="sage",
        concept="A curious occultist who bargains for forbidden power and studies the cracks in reality.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None
    assert constraints.spellcasting.caster_type == "known"
    assert constraints.spellcasting.pact_slot_level == 2

    # Sage grants Arcana + History; warlock chooses 2 more (Deception, Investigation)
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
        featureChoices={
            "warlock-patron": "fiend",
            "warlock-pact-boon": "tome",
        },
        selectedCantrips=["eldritch-blast", "mage-hand"],
        selectedSpells=["hex", "armor-of-agathys", "hellish-rebuke", "misty-step"],
    )

    ok, issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert ok is True, {"issues": issues, "sections": sections}


def test_spell_validation_paladin_l2_half_caster_prepared_formula() -> None:
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="paladin",
        raceId="human",
        level=2,
        backgroundId="soldier",
        concept="A sworn protector who fights on the front line and calls on holy power when allies are in danger.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None
    assert constraints.spellcasting.caster_type == "prepared"
    assert constraints.spellcasting.prepared_formula == "abilityModPlusHalfLevel"

    # CHA 14 => mod +2; half level (2//2=1) => prepared = max(1, 2 + 1) = 3
    choices = ValidationChoices(
        abilityScores=AbilityScores(
            strength=15,
            dexterity=10,
            constitution=14,
            intelligence=8,
            wisdom=10,
            charisma=14,
        ),
        # Soldier grants Athletics + Intimidation; choose 2 more
        selectedSkills=["Athletics", "Intimidation", "Insight", "Persuasion"],
        equipmentPackageId="A",
        featureChoices={
            "paladin-fighting-style": "defense",
        },
        selectedCantrips=[],
        selectedSpells=["bless", "shield-of-faith", "cure-wounds"],
    )

    ok, issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert ok is True, {"issues": issues, "sections": sections}


