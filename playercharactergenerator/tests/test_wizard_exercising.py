from playercharactergenerator.models.pcg_models import AiPreferences, GenerationInput
from playercharactergenerator.rule_engine import PCGRuleEngine
from playercharactergenerator.rule_engine.compute import compute_derived_stats
from playercharactergenerator.rule_engine.translator import translate_preferences
from playercharactergenerator.rule_engine.validators import validate_translated_choices


def _base_prefs_dict(*, name: str) -> dict:
    return {
        "abilityPriorities": ["intelligence", "constitution", "dexterity", "wisdom", "charisma", "strength"],
        "abilityReasoning": "A disciplined mind and steady focus are essential; toughness helps survive mistakes.",
        "combatApproach": "Control the battlefield with clever spells and finish fights safely at range.",
        "skillThemes": ["arcane knowledge", "keen observation", "investigation"],
        "equipmentStyle": "Practical robes, a well-kept spellbook, and a focus that looks academic rather than flashy.",
        "character": {
            "name": name,
            "personality": {
                "traits": ["I catalog everything I learn, even if it annoys others."],
                "ideals": ["Knowledge - Truth is worth pursuing, whatever the cost."],
                "bonds": ["My mentor vanished while researching a forbidden theorem."],
                "flaws": ["I overthink and hesitate when quick action is needed."],
            },
            "backstory": "Raised in a small archive-town, I earned a place with a traveling scholar and learned to bend magic to reason.",
            "appearance": "Ink-stained fingers, sharp eyes, and a calm, precise demeanor.",
            "age": 27,
        },
    }


def test_wizard_high_elf_l1_translate_validate_compute_end_to_end() -> None:
    """
    Exercise the full pipeline for a prepared caster at L1:
    constraints -> translate (including spells) -> validate -> compute.
    """
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="wizard",
        raceId="high-elf",
        level=1,
        backgroundId="sage",
        concept="A meticulous high elf wizard who studies ancient ruins and uses magic to unravel lost histories.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None
    assert constraints.spellcasting.caster_type == "prepared"
    assert constraints.spellcasting.prepared_formula == "abilityModPlusLevel"
    assert constraints.spellcasting.cantrips_known == 3

    pref_dict = _base_prefs_dict(name="Elaria Quillbright")
    pref_dict.update(
        {
            "cantripThemes": ["utility", "damage"],
            "spellThemes": ["protection", "utility", "control"],
        }
    )
    preferences = AiPreferences(**pref_dict)

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues, "choices": choices.model_dump(by_alias=True)}

    # Prepared count = max(1, INT_mod + level). INT should be high from point-buy distribution; enforce expected count from output.
    assert len(choices.selected_cantrips or []) == 3
    assert len(choices.selected_spells or []) >= 1

    valid, v_issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues, "sections": sections}

    ok2, c_issues, derived, c_sections = compute_derived_stats(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert ok2 is True, {"issues": c_issues, "sections": c_sections}
    assert derived is not None
    assert derived.proficiency_bonus == 2


def test_wizard_high_elf_l3_subclass_preference_translate_validate_compute_end_to_end() -> None:
    """
    L3 adds higher spell availability and includes the Arcane Tradition feature choice (level 2).
    This test ensures subclass preference is honored and spell validation passes.
    """
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="wizard",
        raceId="high-elf",
        level=3,
        backgroundId="sage",
        concept="A high elf evoker who believes magic is a tool that should be understood, not feared.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None
    assert constraints.spellcasting.caster_type == "prepared"
    assert constraints.spellcasting.prepared_formula == "abilityModPlusLevel"
    assert constraints.spellcasting.max_spell_level == 2

    pref_dict = _base_prefs_dict(name="Theron of the Seven Sigils")
    pref_dict.update(
        {
            "subclassPreference": {"id": "evocation", "reasoning": "Direct, disciplined application of arcane force."},
            "cantripThemes": ["damage", "utility"],
            "spellThemes": ["damage", "protection", "utility"],
        }
    )
    preferences = AiPreferences(**pref_dict)

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues, "choices": choices.model_dump(by_alias=True)}

    # Feature choices should include wizard-subclass for level >= 2.
    assert "wizard-subclass" in (choices.feature_choices or {})

    valid, v_issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues, "sections": sections}

    ok2, c_issues, derived, c_sections = compute_derived_stats(
        input_data=input_data,
        constraints=constraints,
        choices=choices,
    )
    assert ok2 is True, {"issues": c_issues, "sections": c_sections}
    assert derived is not None
    assert derived.proficiency_bonus == 2


def test_wizard_unmatched_spell_themes_still_fill_counts_and_validate() -> None:
    """
    Stress: nonsensical themes should not break the pipeline; translator should still fill
    required counts from constraints so validator passes.
    """
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="wizard",
        raceId="high-elf",
        level=2,
        backgroundId="sage",
        concept="A wizard who writes strange metaphors about stars, but still needs functional spells.",
    )
    constraints = engine.get_constraints(input_data)
    assert constraints.spellcasting is not None

    pref_dict = _base_prefs_dict(name="Mira Star-scribe")
    pref_dict.update(
        {
            "cantripThemes": ["unicorn-laser", "banana"],
            "spellThemes": ["unicorn-laser", "banana", "time-cube"],
        }
    )
    preferences = AiPreferences(**pref_dict)

    ok, choices, issues = translate_preferences(preferences=preferences, constraints=constraints, level=input_data.level)
    assert ok is True, {"issues": issues, "choices": choices.model_dump(by_alias=True)}

    valid, v_issues, sections = validate_translated_choices(input_data=input_data, constraints=constraints, choices=choices)
    assert valid is True, {"issues": v_issues, "sections": sections}

