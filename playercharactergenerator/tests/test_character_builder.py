from playercharactergenerator.character_builder import build_character_object
from playercharactergenerator.models.pcg_models import AiPreferences, GenerationInput
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.compute import compute_derived_stats
from playercharactergenerator.rule_engine.translator import translate_preferences
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def _prefs_base(**overrides):
    base = {
        "abilityPriorities": ["strength", "constitution", "dexterity", "wisdom", "charisma", "intelligence"],
        "skillThemes": ["battlefield awareness", "physical prowess"],
        "equipmentStyle": "Practical and sturdy equipment.",
        "character": {
            "name": "Generated Hero",
            "personality": {"traits": [], "ideals": [], "bonds": [], "flaws": []},
            "backstory": "A test character created by the generator.",
            "appearance": "N/A",
            "age": 20,
        },
    }
    base.update(overrides)
    return base


def test_build_character_includes_weapons_equipment_and_features_for_fighter() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="fighter",
        raceId="human",
        level=1,
        backgroundId="soldier",
        concept="A disciplined frontline soldier who protects allies.",
    )
    constraints = engine.get_constraints(input_data)

    preferences = AiPreferences(**_prefs_base(fightingStylePreference={"id": "defense"}))

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues}

    valid, v_issues, _sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues}

    ok2, c_issues, derived, _sections2 = compute_derived_stats(input_data=input_data, constraints=constraints, choices=choices)
    assert ok2 is True, {"issues": c_issues}
    assert derived is not None

    character = build_character_object(
        input_data=input_data,
        constraints=constraints,
        preferences=preferences,
        choices=choices,
        derived_stats=derived,
    )

    dnd = character["dnd5eData"]
    assert isinstance(dnd.get("weapons"), list)
    assert len(dnd["weapons"]) >= 1, "Expected at least one weapon for attacks section"
    assert isinstance(dnd.get("equipment"), list)
    # Equipment may be empty for some packages, but should exist and be a list.
    assert "features" in dnd and isinstance(dnd["features"], list)
    assert len(dnd["features"]) >= 1, "Expected at least one feature (e.g., Second Wind / Fighting Style)"


def test_build_character_includes_spellcasting_payload_for_wizard() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="wizard",
        raceId="human",
        level=1,
        backgroundId="sage",
        concept="A scholarly mage who survived the war and now seeks forbidden lore.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None

    preferences = AiPreferences(
        **_prefs_base(
            abilityPriorities=["intelligence", "constitution", "dexterity", "wisdom", "charisma", "strength"],
            cantripThemes=["utility"],
            spellThemes=["protection"],
        )
    )

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues}

    valid, v_issues, _sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues}

    ok2, c_issues, derived, _sections2 = compute_derived_stats(input_data=input_data, constraints=constraints, choices=choices)
    assert ok2 is True, {"issues": c_issues}
    assert derived is not None

    character = build_character_object(
        input_data=input_data,
        constraints=constraints,
        preferences=preferences,
        choices=choices,
        derived_stats=derived,
    )

    dnd = character["dnd5eData"]
    assert dnd.get("spellcasting") is not None
    assert isinstance(dnd["spellcasting"].get("cantrips"), list)
    assert isinstance(dnd["spellcasting"].get("spellsKnown"), list)


def test_build_character_spell_slots_for_bard_level_3() -> None:
    engine = PCGRuleEngine()

    input_data = GenerationInput(
        classId="bard",
        raceId="human",
        level=3,
        backgroundId="sage",
        concept="A romantic bard researching legendary monsters.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None

    preferences = AiPreferences(
        **_prefs_base(
            abilityPriorities=["charisma", "dexterity", "constitution", "intelligence", "wisdom", "strength"],
            spellThemes=["enchantment"],
        )
    )

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues}

    valid, v_issues, _sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues}

    ok2, c_issues, derived, _sections2 = compute_derived_stats(input_data=input_data, constraints=constraints, choices=choices)
    assert ok2 is True, {"issues": c_issues}
    assert derived is not None

    character = build_character_object(
        input_data=input_data,
        constraints=constraints,
        preferences=preferences,
        choices=choices,
        derived_stats=derived,
    )

    dnd = character["dnd5eData"]
    sc = dnd.get("spellcasting") or {}
    slots = sc.get("spellSlots") or {}
    assert slots.get(1, {}).get("total") == 4
    assert slots.get(2, {}).get("total") == 2


