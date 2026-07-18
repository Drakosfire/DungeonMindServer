from datetime import datetime, timezone

from statblocks_v1.application.commands import (
    AssetOptionsV1,
    CallerProvenanceV1,
    GenerateStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.generation import GenerationFailureV1, GenerationServiceV1
from statblocks_v1.application.provider import ProviderOutcomeKind, ProviderOutcomeV1
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository


def _command() -> GenerateStatblockCommandV1:
    return GenerateStatblockCommandV1(
        request_id="req_generation",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="Fixture Bruiser", description="A reliable test creature."),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )


def _service(payload, *, candidate_id="cand_1", asset_generator=None) -> GenerationServiceV1:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return GenerationServiceV1(
        provider=FakeDefinitionProvider(payload),
        candidates=InMemoryCandidateRepository(clock=lambda: now),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: candidate_id,
        asset_generator=asset_generator,
    )


def test_generation_persists_valid_candidate(load_fixture) -> None:
    result = _service(load_fixture("simple_bruiser")).generate(_command())

    assert result.candidate_id == "cand_1"
    assert result.generation_receipt.model == "test-model"
    assert result.generation_receipt.source_description_digest.startswith("sha256:")
    assert result.validation_receipt.is_persistence_ready


def test_provider_outcome_is_typed_failure() -> None:
    result = _service(
        ProviderOutcomeV1(ProviderOutcomeKind.refusal, message="no")
    ).generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "provider_refusal"


def test_reference_invalid_definition_is_not_persisted(load_fixture) -> None:
    result = _service(load_fixture("dangling_multiattack_ref")).generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "definition_invalid"


def test_asset_failure_preserves_valid_candidate(load_fixture) -> None:
    class FailingAssets:
        def generate(self, brief):
            raise RuntimeError("image unavailable")

    command = _command().model_copy(
        update={"asset_options": AssetOptionsV1(generate_images=True)}
    )
    result = _service(load_fixture("simple_bruiser"), asset_generator=FailingAssets()).generate(command)

    assert result.candidate_id == "cand_1"
    assert result.assets == []
    assert result.asset_warnings
