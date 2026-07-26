from __future__ import annotations

import json
from pathlib import Path

from statblocks_v1.api.models import ErrorEnvelopeV1, ReviseCandidateRequestV1
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1

API_FIXTURE_DIRECTORY = (
    Path(__file__).parents[2]
    / "Docs"
    / "Design"
    / "fixtures"
    / "dungeonbuddy-statblock-v1-api"
)


def _load(name: str) -> dict:
    return json.loads((API_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8"))


def test_revise_request_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-request.json")
    assert "_note" not in raw
    request = ReviseCandidateRequestV1.model_validate(raw)
    assert request.request_id == "fixture-revise-source-def-1"
    assert request.source_definition is not None
    assert request.source_locator is None
    assert request.revision_instructions == ["Tighten melee damage for table pace."]
    assert request.model_dump(mode="json") == raw


def test_revise_replay_response_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-replay-response.json")
    assert "_note" not in raw
    candidate = GeneratedStatblockCandidateV1.model_validate(raw)
    assert candidate.candidate_id == "cand_fix00000001"
    assert candidate.definition is not None
    assert candidate.validation_receipt is not None
    assert candidate.generation_receipt is not None
    assert candidate.generation_receipt.request_id == "fixture-revise-source-def-1"
    assert candidate.generation_receipt.request_digest.startswith("sha256:")
    assert candidate.model_dump(mode="json") == raw


def test_revise_conflict_response_fixture_is_strict_model_valid() -> None:
    raw = _load("revise-conflict-response.json")
    assert "_note" not in raw
    envelope = ErrorEnvelopeV1.model_validate(raw)
    assert envelope.error.code == "idempotency_conflict"
    assert envelope.error.message == "Idempotency key was reused with a different request"
    assert envelope.error.details == {"idempotency_key": "fixture-revise-source-def-1"}
    assert envelope.model_dump(mode="json") == raw
