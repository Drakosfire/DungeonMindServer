from statblocks_v1.application.commands import (
    CallerProvenanceV1,
    GenerateStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.prompts import PROMPT_VERSION, build_generation_prompt
from statblocks_v1.domain.profiles import RulesetRef


def test_generation_prompt_is_versioned_definition_only() -> None:
    prompt = build_generation_prompt(
        GenerateStatblockCommandV1(
            request_id="req_prompt",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            source=SourceSnapshotV1(name_hint="Gate Warden", description="Guards a narrow gate."),
            caller=CallerProvenanceV1(caller_scope="test"),
        )
    )

    assert PROMPT_VERSION == "statblock-generation-prompt-v1"
    assert "2024 D&D 5e" in prompt
    assert "human_adjudicated" in prompt
    assert "candidate IDs" in prompt
