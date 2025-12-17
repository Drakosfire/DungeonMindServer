from playercharactergenerator.models.pcg_models import GenerationInput
from playercharactergenerator.rule_engine import PCGRuleEngine


def test_barbarian_constraints_build() -> None:
    engine = PCGRuleEngine()
    input_data = GenerationInput(
        classId="barbarian",
        raceId="human",
        level=1,
        backgroundId="soldier",
        concept="A fierce warrior who relies on raw strength and grit rather than discipline or magic.",
    )

    constraints = engine.get_constraints(input_data)
    assert constraints.class_info.id == "barbarian"
    assert constraints.class_info.name == "Barbarian"
    assert constraints.class_info.hit_die == 12

    # Skills: soldier grants 2, barbarian choose 2 => total expected 4 in validator, but constraints just exposes options/count.
    assert constraints.skills.choose_count == 2
    assert "Athletics" in constraints.skills.class_options

    # Equipment packages should exist (v0 shape is constraints.equipment["packages"])
    packages = constraints.equipment.get("packages", [])
    assert len(packages) >= 1

