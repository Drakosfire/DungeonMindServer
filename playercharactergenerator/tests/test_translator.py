from playercharactergenerator.models.pcg_models import AiPreferences, GenerationInput
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.compute import compute_derived_stats
from playercharactergenerator.rule_engine.translator import translate_preferences
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def test_translate_preferences_fighter_end_to_end_validates_and_computes() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="fighter",
        raceId="human",
        level=1,
        backgroundId="soldier",
        concept="A battle-hardened veteran seeking redemption after a war gone wrong.",
    )
    constraints = engine.get_constraints(input_data)

    pref_dict = {
        "abilityPriorities": ["strength", "constitution", "dexterity", "wisdom", "charisma", "intelligence"],
        "skillThemes": ["physical prowess", "intimidation", "battlefield awareness"],
        "equipmentStyle": "Heavy armor with shield for maximum protection.",
        "fightingStylePreference": {"id": "defense"},
        "character": {
            "name": "Kira Stonefist",
            "personality": {
                "traits": ["I face problems head-on, no matter the odds"],
                "ideals": ["Protection - The strong must shield the weak"],
                "bonds": ["I carry the insignia of my fallen unit."],
                "flaws": ["I blame myself for every death I witness."],
            },
            "backstory": "Kira served in the Iron Legion and now wanders seeking redemption.",
            "appearance": "Weathered human veteran with a jagged scar.",
            "age": 38,
        },
    }
    preferences = AiPreferences(**pref_dict)

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues, "choices": choices.model_dump(by_alias=True)}

    valid, v_issues, sections = validate_translated_choices(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert valid is True, {"issues": v_issues, "sections": sections}

    ok2, c_issues, derived, _sections = compute_derived_stats(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert ok2 is True, {"issues": c_issues}
    assert derived is not None


def test_translate_preferences_wizard_spellcounts_validate() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="wizard",
        raceId="human",
        level=1,
        backgroundId="sage",
        concept="A scholarly mage who survived the war and now seeks forbidden lore.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None, "Wizard should have spellcasting constraints at level 1"

    pref_dict = {
        "abilityPriorities": ["intelligence", "constitution", "dexterity", "wisdom", "charisma", "strength"],
        "skillThemes": ["arcane knowledge", "scholarly research", "keen observation"],
        "equipmentStyle": "Light and practical - a quarterstaff for emergencies.",
        "cantripThemes": ["damage", "utility"],
        "spellThemes": ["protection", "reliable damage"],
        "character": {
            "name": "Aldric Thornwood",
            "personality": {"traits": [], "ideals": [], "bonds": [], "flaws": []},
            "backstory": "Aldric carries his mentor's spellbook into a dangerous world.",
            "appearance": "Ink-stained scholar with spectacles.",
            "age": 24,
        },
    }
    preferences = AiPreferences(**pref_dict)

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues, "choices": choices.model_dump(by_alias=True)}

    valid, v_issues, sections = validate_translated_choices(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert valid is True, {"issues": v_issues, "sections": sections}




