from __future__ import annotations

import copy
import math
from datetime import datetime, timezone

import pytest

from statblocks_v1.application.commands import (
    AssetOptionsV1,
    CallerProvenanceV1,
    EncounterContextV1,
    GenerateStatblockCommandV1,
    GenerationIntentV1,
    ReviseStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.generation import (
    KEY_PRESERVATION_PASS_VERSION,
    GenerationFailureV1,
    GenerationServiceV1,
    _digest_text,
)
from statblocks_v1.application.provider import ProviderOutcomeKind, ProviderOutcomeV1
from statblocks_v1.application.repositories import CreateStatblockCommand
from statblocks_v1.application.resolvers import PersistenceDefinitionResolver
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.errors import InternalServiceMisconfiguredError, RevisionNotFoundError
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.receipts import ValidationStatus
from statblocks_v1.domain.resources import AssetWarningCode, ExactRevisionLocatorV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import (
    DeterministicIdFactory,
    InMemoryCandidateRepository,
    InMemoryStatblockPersistenceRepository,
)


def _command(**overrides) -> GenerateStatblockCommandV1:
    base = dict(
        request_id="req_generation",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="Fixture Bruiser", description="A reliable test creature."),
        caller=CallerProvenanceV1(caller_scope="tests", actor="unit"),
    )
    base.update(overrides)
    return GenerateStatblockCommandV1(**base)


def _service(
    payload,
    *,
    candidate_id="cand_1",
    asset_generator=None,
    definition_resolver=None,
    candidates=None,
) -> GenerationServiceV1:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return GenerationServiceV1(
        provider=FakeDefinitionProvider(payload),
        candidates=candidates or InMemoryCandidateRepository(clock=lambda: now),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: candidate_id,
        asset_generator=asset_generator,
        definition_resolver=definition_resolver,
    )


def test_generation_persists_valid_candidate(load_fixture) -> None:
    candidates = InMemoryCandidateRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    result = _service(load_fixture("simple_bruiser"), candidates=candidates).generate(_command())

    assert not isinstance(result, GenerationFailureV1)
    assert result.candidate_id == "cand_1"
    assert result.generation_receipt.model == "test-model"
    assert result.generation_receipt.caller_scope == "tests"
    assert result.generation_receipt.actor == "unit"
    assert result.generation_receipt.source_description_digest == _digest_text(
        "A reliable test creature."
    )
    assert result.validation_receipt.status is ValidationStatus.valid
    assert candidates.get("cand_1").candidate_id == "cand_1"


def test_advanced_fixture_generation_persists(load_fixture) -> None:
    result = _service(load_fixture("legendary_creature"), candidate_id="cand_adv").generate(
        _command(source=SourceSnapshotV1(name_hint="Legend", description="A mythic threat."))
    )

    assert not isinstance(result, GenerationFailureV1)
    assert result.candidate_id == "cand_adv"
    assert result.definition.identity.name


def test_warning_bearing_candidate_is_persisted(load_fixture) -> None:
    payload = copy.deepcopy(load_fixture("simple_bruiser"))
    payload["rule_elements"][0]["rules_text"] = (
        "Melee Weapon Attack: +99 to hit, reach 10 ft., one target. "
        "Hit: 11 (2d8 + 2) bludgeoning damage."
    )
    result = _service(payload).generate(_command())

    assert not isinstance(result, GenerationFailureV1)
    assert result.validation_receipt.status is ValidationStatus.warnings
    assert any(
        issue.code == "RULES_TEXT_ATTACK_BONUS_MISMATCH"
        for issue in result.validation_receipt.issues
    )


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (ProviderOutcomeKind.refusal, "provider_refusal"),
        (ProviderOutcomeKind.incomplete, "provider_incomplete"),
        (ProviderOutcomeKind.timeout, "provider_timeout"),
        (ProviderOutcomeKind.rate_limit, "provider_rate_limit"),
        (ProviderOutcomeKind.failure, "provider_failure"),
    ],
)
def test_provider_outcomes_are_typed_failures(kind, expected) -> None:
    result = _service(ProviderOutcomeV1(kind, message="no")).generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == expected


def test_provider_exception_is_typed_failure(load_fixture) -> None:
    class ExplodingProvider:
        provider_name = "boom"

        def generate_definition(self, **kwargs):
            raise RuntimeError("sdk exploded")

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = GenerationServiceV1(
        provider=ExplodingProvider(),
        candidates=InMemoryCandidateRepository(clock=lambda: now),
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_x",
    )
    result = service.generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "provider_failure"


def test_reference_invalid_definition_is_not_persisted(load_fixture) -> None:
    result = _service(load_fixture("dangling_multiattack_ref")).generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "definition_invalid"


def test_ruleset_mismatch_is_rejected(load_fixture) -> None:
    payload = copy.deepcopy(load_fixture("simple_bruiser"))
    payload["ruleset"]["edition"] = "2014"
    result = _service(payload).generate(_command(ruleset=RulesetRef(system="dnd5e", edition="2024")))

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "ruleset_mismatch"


def test_caller_source_digest_must_match_description() -> None:
    result = _service({}).generate(
        _command(
            source=SourceSnapshotV1(
                name_hint="Fixture Bruiser",
                description="A reliable test creature.",
                description_digest="sha256:" + ("0" * 64),
            )
        )
    )

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "source_digest_mismatch"


def test_verified_source_digest_is_stored(load_fixture) -> None:
    description = "A reliable test creature."
    digest = _digest_text(description)
    result = _service(load_fixture("simple_bruiser")).generate(
        _command(source=SourceSnapshotV1(name_hint="Fixture Bruiser", description=description, description_digest=digest))
    )

    assert not isinstance(result, GenerationFailureV1)
    assert result.generation_receipt.source_description_digest == digest


def test_asset_failure_preserves_valid_candidate(load_fixture) -> None:
    class FailingAssets:
        def generate(self, brief):
            raise RuntimeError("image unavailable")

    command = _command(asset_options=AssetOptionsV1(generate_images=True))
    result = _service(load_fixture("simple_bruiser"), asset_generator=FailingAssets()).generate(command)

    assert not isinstance(result, GenerationFailureV1)
    assert result.assets == []
    assert [warning.code for warning in result.asset_warnings] == [
        AssetWarningCode.asset_generation_failed
    ]
    assert result.asset_brief is not None
    assert result.asset_brief["prompt"] == "A reliable test creature."


def test_requested_assets_without_generator_warn(load_fixture) -> None:
    command = _command(asset_options=AssetOptionsV1(generate_images=True))
    result = _service(load_fixture("simple_bruiser")).generate(command)

    assert not isinstance(result, GenerationFailureV1)
    assert result.assets == []
    assert [warning.code for warning in result.asset_warnings] == [
        AssetWarningCode.asset_generator_unconfigured
    ]
    assert result.asset_brief is not None


def test_generate_images_persists_effective_brief_without_description_brief(load_fixture) -> None:
    class CapturingAssets:
        def __init__(self) -> None:
            self.brief = None

        def generate(self, brief):
            self.brief = brief
            return [{"role": "portrait", "url": "https://example.test/p.png"}]

    assets = CapturingAssets()
    command = _command(
        asset_options=AssetOptionsV1(generate_images=True, include_generation_brief=False)
    )
    result = _service(load_fixture("simple_bruiser"), asset_generator=assets).generate(command)

    assert not isinstance(result, GenerationFailureV1)
    assert assets.brief is not None
    assert result.asset_brief == assets.brief.model_dump(mode="json")
    assert result.asset_brief["prompt"] == result.definition.identity.name
    assert result.asset_warnings == []


def test_typed_asset_warnings_round_trip_through_candidate_repository(load_fixture) -> None:
    candidates = InMemoryCandidateRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    command = _command(asset_options=AssetOptionsV1(generate_images=True))
    created = _service(
        load_fixture("simple_bruiser"), candidates=candidates, candidate_id="cand_warn"
    ).generate(command)

    assert not isinstance(created, GenerationFailureV1)
    loaded = candidates.get("cand_warn")
    assert [warning.code for warning in loaded.asset_warnings] == [
        AssetWarningCode.asset_generator_unconfigured
    ]
    assert loaded.asset_brief == created.asset_brief


def test_revision_from_definition_preserves_keys(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    revised = source.model_copy(deep=True)
    result = _service(revised.model_dump(mode="json")).revise(
        ReviseStatblockCommandV1(
            request_id="req_revise",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["Keep the club attack"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source,
            intent=GenerationIntentV1(must_include=["club"]),
            context=EncounterContextV1(terrain_notes=["gate"]),
            preserve_element_keys=True,
        )
    )

    assert not isinstance(result, GenerationFailureV1)
    assert {element.key for element in result.definition.rule_elements} == {
        element.key for element in source.rule_elements
    }
    assert result.generation_receipt.source_definition_digest == compute_definition_digest(source)
    assert KEY_PRESERVATION_PASS_VERSION in result.validation_receipt.validator_version
    assert not any(
        issue.code.startswith("ELEMENT_KEY_") for issue in result.validation_receipt.issues
    )


def test_inline_revision_source_definition_digests_differ(load_fixture) -> None:
    source_a = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    source_b_payload = source_a.model_dump(mode="json")
    source_b_payload["identity"]["name"] = "Fixture Bruiser Variant"
    source_b = StatblockDefinitionV1.model_validate(source_b_payload)
    shared_source = SourceSnapshotV1(
        name_hint="Shared",
        description="Same authored prose for both revisions.",
    )

    result_a = _service(source_a.model_dump(mode="json")).revise(
        ReviseStatblockCommandV1(
            request_id="req_a",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["noop"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source_a,
            source=shared_source,
        )
    )
    result_b = _service(source_b.model_dump(mode="json"), candidate_id="cand_b").revise(
        ReviseStatblockCommandV1(
            request_id="req_b",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["noop"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source_b,
            source=shared_source,
        )
    )

    assert not isinstance(result_a, GenerationFailureV1)
    assert not isinstance(result_b, GenerationFailureV1)
    assert result_a.generation_receipt.source_description_digest == (
        result_b.generation_receipt.source_description_digest
    )
    assert result_a.generation_receipt.source_definition_digest == compute_definition_digest(
        source_a
    )
    assert result_b.generation_receipt.source_definition_digest == compute_definition_digest(
        source_b
    )
    assert (
        result_a.generation_receipt.source_definition_digest
        != result_b.generation_receipt.source_definition_digest
    )


def test_revision_key_change_warns_when_preserve_enabled(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    revised_payload = source.model_dump(mode="json")
    revised_payload["rule_elements"][0]["key"] = "renamed_club"
    result = _service(revised_payload).revise(
        ReviseStatblockCommandV1(
            request_id="req_revise_keys",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["Rename the attack key"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source,
            preserve_element_keys=True,
        )
    )

    assert not isinstance(result, GenerationFailureV1)
    assert any(issue.code == "ELEMENT_KEY_CHANGED" for issue in result.validation_receipt.issues)


def test_revision_key_repurposed_warns_when_preserve_enabled(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    revised_payload = source.model_dump(mode="json")
    original_key = revised_payload["rule_elements"][0]["key"]
    revised_payload["rule_elements"][0]["name"] = "Fire Breath"
    revised_payload["rule_elements"][0]["key"] = original_key
    result = _service(revised_payload).revise(
        ReviseStatblockCommandV1(
            request_id="req_revise_repurpose",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["Replace the club with fire breath but keep the key"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source,
            preserve_element_keys=True,
        )
    )

    assert not isinstance(result, GenerationFailureV1)
    codes = {issue.code for issue in result.validation_receipt.issues}
    assert "ELEMENT_KEY_REPURPOSED" in codes
    assert "ELEMENT_KEY_DROPPED" not in codes


def test_revision_duplicate_identity_is_ambiguous_not_misattributed(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    source_payload = source.model_dump(mode="json")
    duplicate = copy.deepcopy(source_payload["rule_elements"][0])
    duplicate["key"] = "club_duplicate"
    source_payload["rule_elements"].append(duplicate)
    source_with_dupes = StatblockDefinitionV1.model_validate(source_payload)

    revised_payload = source_with_dupes.model_dump(mode="json")
    revised_payload["rule_elements"][0]["key"] = "renamed_first"
    revised_payload["rule_elements"][1]["key"] = "renamed_second"
    result = _service(revised_payload).revise(
        ReviseStatblockCommandV1(
            request_id="req_ambiguous",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["Rename duplicate clubs"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_definition=source_with_dupes,
            preserve_element_keys=True,
        )
    )

    assert not isinstance(result, GenerationFailureV1)
    codes = [issue.code for issue in result.validation_receipt.issues]
    assert "ELEMENT_KEY_IDENTITY_AMBIGUOUS" in codes
    assert "ELEMENT_KEY_CHANGED" not in codes


def test_revision_from_exact_locator(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        id_factory=DeterministicIdFactory(),
    )
    statblock, revision = persistence.create_statblock(
        CreateStatblockCommand(
            caller_scope="tests",
            idempotency_key="create-revision-source",
            definition=definition,
            created_by="tests",
        )
    )
    locator = ExactRevisionLocatorV1(
        statblock_id=statblock.statblock_id, revision_id=revision.revision_id
    )
    result = _service(
        definition.model_dump(mode="json"),
        definition_resolver=PersistenceDefinitionResolver(persistence),
    ).revise(
        ReviseStatblockCommandV1(
            request_id="req_locate",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["Tighten the club damage"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_locator=locator,
        )
    )

    assert not isinstance(result, GenerationFailureV1)
    assert result.source_locator == locator
    assert result.generation_receipt.source_locator == locator
    assert result.generation_receipt.source_definition_digest == revision.definition_digest
    assert result.generation_receipt.source_definition_digest == compute_definition_digest(
        definition
    )


def test_revision_resolver_errors_are_typed(load_fixture) -> None:
    class BrokenResolver:
        def resolve(self, locator):
            raise RevisionNotFoundError(locator.revision_id)

    result = _service(load_fixture("simple_bruiser"), definition_resolver=BrokenResolver()).revise(
        ReviseStatblockCommandV1(
            request_id="req_missing",
            ruleset=RulesetRef(system="dnd5e", edition="2024"),
            revision_instructions=["noop"],
            caller=CallerProvenanceV1(caller_scope="tests"),
            source_locator=ExactRevisionLocatorV1(statblock_id="sb_1", revision_id="rev_missing"),
        )
    )

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "revision_not_found"


def test_settings_resolve_in_repo_model_policy(monkeypatch) -> None:
    monkeypatch.delenv("STATBLOCKS_V1_OPENAI_MODEL", raising=False)
    settings = GenerationSettingsV1.from_environment()
    assert settings.model == "gpt-5.4-nano"


def test_settings_fail_closed_without_policy(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("STATBLOCKS_V1_OPENAI_MODEL", raising=False)
    monkeypatch.setattr(
        "statblocks_v1.application.settings._REPO_ROOT",
        tmp_path,
    )
    with pytest.raises(InternalServiceMisconfiguredError):
        GenerationSettingsV1.from_environment()


@pytest.mark.parametrize(
    ("env_name", "env_value"),
    [
        ("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", "garbage"),
        ("STATBLOCKS_V1_OPENAI_MAX_RETRIES", "1.5"),
        ("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", "nope"),
    ],
)
def test_settings_malformed_env_is_typed(monkeypatch, env_name, env_value) -> None:
    monkeypatch.setenv("STATBLOCKS_V1_OPENAI_MODEL", "test-model")
    monkeypatch.setenv(env_name, env_value)
    with pytest.raises(InternalServiceMisconfiguredError, match="malformed"):
        GenerationSettingsV1.from_environment()


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"model": "", "timeout_seconds": 1.0, "max_retries": 0, "candidate_ttl_seconds": 60}, "MODEL"),
        ({"model": "m", "timeout_seconds": 0.0, "max_retries": 0, "candidate_ttl_seconds": 60}, "TIMEOUT"),
        ({"model": "m", "timeout_seconds": -1.0, "max_retries": 0, "candidate_ttl_seconds": 60}, "TIMEOUT"),
        ({"model": "m", "timeout_seconds": math.nan, "max_retries": 0, "candidate_ttl_seconds": 60}, "TIMEOUT"),
        ({"model": "m", "timeout_seconds": math.inf, "max_retries": 0, "candidate_ttl_seconds": 60}, "TIMEOUT"),
        ({"model": "m", "timeout_seconds": 1.0, "max_retries": -1, "candidate_ttl_seconds": 60}, "RETRIES"),
        ({"model": "m", "timeout_seconds": 1.0, "max_retries": 0, "candidate_ttl_seconds": 0}, "TTL"),
        ({"model": "m", "timeout_seconds": 1.0, "max_retries": 0, "candidate_ttl_seconds": -5}, "TTL"),
    ],
)
def test_settings_direct_construction_fails_closed(kwargs, match) -> None:
    with pytest.raises(InternalServiceMisconfiguredError, match=match):
        GenerationSettingsV1(**kwargs)
