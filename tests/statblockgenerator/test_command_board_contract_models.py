import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from statblockgenerator.models.command_board_contract_models import StatBlockDraftRequest

FIXTURE_DIR = Path("Docs/Design/fixtures/statblockgenerator-command-board-contract")


@pytest.mark.parametrize("fixture_path", sorted(FIXTURE_DIR.glob("*.json")))
def test_command_board_fixtures_validate(fixture_path):
    payload = json.loads(fixture_path.read_text())

    request = StatBlockDraftRequest.model_validate(payload)

    assert request.request_id == payload["request_id"]
    assert request.mode == payload["mode"]
    assert request.output_options.persist is False


def test_output_options_persist_defaults_false_when_omitted():
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    payload.pop("output_options")

    request = StatBlockDraftRequest.model_validate(payload)

    assert request.output_options.persist is False


def test_invalid_mode_fails_clearly():
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    payload["mode"] = "invent_a_mode"

    with pytest.raises(ValidationError) as exc_info:
        StatBlockDraftRequest.model_validate(payload)

    assert "mode" in str(exc_info.value)


def test_prompt_required_for_prompt_generation_modes():
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    payload["prompt"] = ""

    with pytest.raises(ValidationError) as exc_info:
        StatBlockDraftRequest.model_validate(payload)

    assert "prompt is required" in str(exc_info.value)


def test_empty_prompt_allowed_when_source_context_is_sufficient():
    payload = json.loads((FIXTURE_DIR / "revise_existing.latch_harrow_weaker.json").read_text())
    payload["prompt"] = ""

    request = StatBlockDraftRequest.model_validate(payload)

    assert request.mode == "revise_existing"
    assert request.source_statblock is not None
