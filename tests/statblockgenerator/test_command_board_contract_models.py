import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from statblockgenerator.models.command_board_contract_models import ContractError, StatBlockDraftResponse, StatBlockDraftRequest

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "Docs/Design/fixtures/statblockgenerator-command-board-contract"
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))
assert FIXTURE_PATHS, f"No command-board contract fixtures found in {FIXTURE_DIR}"


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS)
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


def test_render_existing_mode_requires_source_statblock():
    payload = json.loads((FIXTURE_DIR / "generate_from_prompt.basic.json").read_text())
    payload["mode"] = "render_existing"
    payload["prompt"] = None
    payload["source_statblock"] = None

    with pytest.raises(ValidationError) as exc_info:
        StatBlockDraftRequest.model_validate(payload)

    assert "render_existing" in str(exc_info.value)
    assert "source_statblock" in str(exc_info.value)


def test_success_response_requires_draft():
    with pytest.raises(ValidationError) as exc_info:
        StatBlockDraftResponse(success=True)

    assert "successful draft responses require draft" in str(exc_info.value)


def test_failure_response_requires_error():
    with pytest.raises(ValidationError) as exc_info:
        StatBlockDraftResponse(success=False)

    assert "failed draft responses require error" in str(exc_info.value)


def test_failure_response_accepts_error_envelope():
    response = StatBlockDraftResponse(
        success=False,
        error=ContractError(code="generation_failed", message="Generation failed"),
    )

    assert response.error.code == "generation_failed"
