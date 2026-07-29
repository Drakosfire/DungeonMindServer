from statblocks_v1.application.commands import (
    CallerProvenanceV1,
    EncounterContextV1,
    GenerateStatblockCommandV1,
    GenerationIntentV1,
    ReviseStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.prompts import (
    PROMPT_VERSION,
    build_generation_prompt,
    build_revision_prompt,
    build_system_prompt,
)
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


def test_generation_prompt_is_versioned_definition_only() -> None:
    command = GenerateStatblockCommandV1(
        request_id="req_prompt",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="Gate Warden", description="Guards a narrow gate."),
        caller=CallerProvenanceV1(caller_scope="test"),
        intent=GenerationIntentV1(must_avoid=["flight"]),
    )
    prompt = build_generation_prompt(command)
    system = build_system_prompt(command.ruleset.edition.value)

    assert PROMPT_VERSION == "statblock-generation-prompt-v2"
    assert "Gate Warden" in prompt
    assert "Guards a narrow gate." in prompt
    assert "must avoid=flight" in prompt
    assert "You produce only a StatblockDefinitionV1" not in prompt
    assert "candidate IDs" not in prompt
    assert "definition.ruleset.system" not in prompt
    assert "2024 D&D 5e" in system
    assert "recharge                       recharge_range REQUIRED" in system
    assert "defenses.armor_classes: exactly one profile has default=true" in system
    assert 'automation_support "manual"' in system


def test_revision_prompt_includes_intent_context_and_preservation(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    prompt = build_revision_prompt(
        ReviseStatblockCommandV1(
            request_id="req_rev_prompt",
            ruleset=RulesetRef(system="dnd5e", edition="2014"),
            revision_instructions=["Increase CR"],
            caller=CallerProvenanceV1(caller_scope="test"),
            source_definition=source,
            intent=GenerationIntentV1(target_cr="5", roles=["brute"]),
            context=EncounterContextV1(party_level=4, terrain_notes=["ruins"]),
            preserve_element_keys=True,
        ),
        source,
    )
    system = build_system_prompt("2014")

    assert "Increase CR" in prompt
    assert "Preserve existing rule-element local keys" in prompt
    assert "target CR=5" in prompt
    assert "roles=brute" in prompt
    assert "ruins" in prompt
    assert "Source definition JSON:" in prompt
    assert "You produce only a StatblockDefinitionV1" not in prompt
    assert "2014 D&D 5e" in system
    assert "human_adjudicated" in system
