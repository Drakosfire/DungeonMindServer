from __future__ import annotations

import copy
import math
import threading
from concurrent.futures import ThreadPoolExecutor
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
    GenerateOutcomeV1,
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
from statblocks_v1.domain.profiles import RulesetEdition, RulesetRef
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
    asset_gateway=None,
    definition_resolver=None,
    candidates=None,
    generate_operations=None,
    revise_operations=None,
    clock=None,
    provider=None,
) -> GenerationServiceV1:
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRevisionOperationRepository,
    )

    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock_fn = clock or (lambda: fixed)
    candidate_repo = candidates or InMemoryCandidateRepository(clock=clock_fn)
    gen_ops = generate_operations or InMemoryCandidateGenerationOperationRepository(
        candidate_repo, clock=clock_fn
    )
    rev_ops = revise_operations or InMemoryCandidateRevisionOperationRepository(
        candidate_repo, clock=clock_fn
    )
    counter = {"n": 0}

    def next_candidate_id() -> str:
        counter["n"] += 1
        if counter["n"] == 1:
            return candidate_id
        prefix, _, rest = candidate_id.partition("_")
        if rest.isdigit():
            return f"{prefix}_{int(rest) + counter['n'] - 1}"
        return f"{candidate_id}_{counter['n']}"

    return GenerationServiceV1(
        provider=provider or FakeDefinitionProvider(payload),
        candidates=candidate_repo,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=clock_fn,
        candidate_id_factory=next_candidate_id,
        asset_gateway=asset_gateway,
        definition_resolver=definition_resolver,
        generate_operations=gen_ops,
        revise_operations=rev_ops,
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
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
    )

    service = GenerationServiceV1(
        provider=ExplodingProvider(),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_x",
        generate_operations=InMemoryCandidateGenerationOperationRepository(
            candidates, clock=lambda: now
        ),
    )
    result = service.generate(_command())

    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "provider_failure"


def test_generate_without_operations_repository_fails_closed(load_fixture) -> None:
    """Missing generate_operations must not allocate candidates under the request path."""

    class TrackingProvider:
        provider_name = "track"

        def __init__(self) -> None:
            self.calls = 0

        def generate_definition(self, **kwargs):
            self.calls += 1
            raise AssertionError("provider must not be called without ops repo")

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    provider = TrackingProvider()
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_x",
        generate_operations=None,
    )
    first = service.generate(_command())
    second = service.generate(_command())

    assert isinstance(first, GenerationFailureV1)
    assert first.kind == "persistence_unavailable"
    assert isinstance(second, GenerationFailureV1)
    assert second.kind == "persistence_unavailable"
    assert provider.calls == 0
    assert candidates._candidates == {}


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
    result = _service(load_fixture("simple_bruiser"), asset_gateway=FailingAssets()).generate(command)

    assert not isinstance(result, GenerationFailureV1)
    assert result.assets == []
    assert [warning.code for warning in result.asset_warnings] == [
        AssetWarningCode.asset_generation_failed
    ]
    assert result.asset_brief is not None
    assert result.asset_brief.prompt == "A reliable test creature."


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
            return []

    assets = CapturingAssets()
    command = _command(
        asset_options=AssetOptionsV1(generate_images=True, include_generation_brief=False)
    )
    result = _service(load_fixture("simple_bruiser"), asset_gateway=assets).generate(command)

    assert not isinstance(result, GenerationFailureV1)
    assert assets.brief is not None
    assert result.asset_brief == assets.brief
    assert result.asset_brief.prompt == result.definition.identity.name
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


def test_concurrent_command_mutation_cannot_alter_pinned_revise_intent(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    expected_digest = compute_definition_digest(source)
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        id_factory=DeterministicIdFactory(),
    )
    statblock, revision = persistence.create_statblock(
        CreateStatblockCommand(
            caller_scope="tests",
            idempotency_key="pin-revision-source",
            definition=source,
            created_by="tests",
        )
    )
    locator = ExactRevisionLocatorV1(
        statblock_id=statblock.statblock_id, revision_id=revision.revision_id
    )
    command = ReviseStatblockCommandV1(
        request_id="req_pinned",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Keep the club"],
        caller=CallerProvenanceV1(caller_scope="tests", actor="original"),
        source_locator=locator,
        source=SourceSnapshotV1(
            name_hint="Pinned",
            description="Pinned revision description.",
        ),
        asset_options=AssetOptionsV1(generate_images=True, include_generation_brief=True),
        preserve_element_keys=True,
    )

    entered = threading.Event()
    release = threading.Event()
    payload = source.model_dump(mode="json")

    def blocking_callback(prompt, schema, options):
        entered.set()
        assert release.wait(timeout=2)
        return ProviderOutcomeV1.succeeded(payload)

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRevisionOperationRepository,
    )

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider({}, callback=blocking_callback),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_pinned",
        definition_resolver=PersistenceDefinitionResolver(persistence),
        revise_operations=InMemoryCandidateRevisionOperationRepository(
            candidates, clock=lambda: now
        ),
    )

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.revise, command)
        assert entered.wait(timeout=2)
        # Mutate every caller-owned field while the provider is blocked.
        command.request_id = "req_hijacked"
        command.ruleset.edition = RulesetEdition.edition_2014
        command.caller.caller_scope = "hijacked"
        command.caller.actor = "mutated"
        command.source.description = "Mutated description that must not affect digests."
        command.asset_options.generate_images = False
        command.preserve_element_keys = False
        command.source_locator = ExactRevisionLocatorV1(
            statblock_id="sb_hijacked01", revision_id="rev_hijacked01"
        )
        command.revision_instructions[:] = ["Hijacked instructions"]
        release.set()
        result = future.result(timeout=2)

    assert not isinstance(result, GenerationFailureV1)
    assert result.generation_receipt.request_id == "req_pinned"
    assert result.generation_receipt.caller_scope == "tests"
    assert result.generation_receipt.actor == "original"
    assert result.generation_receipt.source_definition_digest == expected_digest
    assert result.generation_receipt.source_description_digest == _digest_text(
        "Pinned revision description."
    )
    assert result.generation_receipt.source_locator == locator
    assert result.source_locator == locator
    assert result.asset_brief is not None
    assert result.asset_brief.prompt == "Pinned revision description."
    assert [warning.code for warning in result.asset_warnings] == [
        AssetWarningCode.asset_generator_unconfigured
    ]
    assert KEY_PRESERVATION_PASS_VERSION in result.validation_receipt.validator_version

    result.generation_receipt.caller_scope = "returned-mutated"
    stored = candidates.get("cand_pinned")
    assert stored.generation_receipt.caller_scope == "tests"
    assert stored.generation_receipt.source_definition_digest == expected_digest
    assert stored.generation_receipt.source_locator == locator


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


class _TrackingDefinitionResolver:
    """Counts resolve() calls; optional hard failure after a completed revise replay path."""

    def __init__(self, inner, *, fail: bool = False) -> None:
        self._inner = inner
        self.fail = fail
        self.resolve_calls = 0

    def resolve(self, locator):
        self.resolve_calls += 1
        if self.fail:
            raise RevisionNotFoundError(locator.revision_id)
        return self._inner.resolve(locator)


def _revision_locator_setup(load_fixture):
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    persistence = InMemoryStatblockPersistenceRepository(
        clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        id_factory=DeterministicIdFactory(),
    )
    statblock, revision = persistence.create_statblock(
        CreateStatblockCommand(
            caller_scope="tests",
            idempotency_key="locator-revise-source",
            definition=definition,
            created_by="tests",
        )
    )
    locator = ExactRevisionLocatorV1(
        statblock_id=statblock.statblock_id, revision_id=revision.revision_id
    )
    return definition, persistence, locator


def test_revise_locator_replay_skips_resolver_after_completion(load_fixture) -> None:
    definition, persistence, locator = _revision_locator_setup(load_fixture)
    inner = PersistenceDefinitionResolver(persistence)
    tracking = _TrackingDefinitionResolver(inner)
    provider = FakeDefinitionProvider(definition.model_dump(mode="json"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRevisionOperationRepository,
    )

    rev_ops = InMemoryCandidateRevisionOperationRepository(candidates, clock=lambda: now)
    command = ReviseStatblockCommandV1(
        request_id="req_locator_replay",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Tighten the club damage"],
        caller=CallerProvenanceV1(caller_scope="tests"),
        source_locator=locator,
    )
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_locreplay1",
        definition_resolver=tracking,
        revise_operations=rev_ops,
    )
    first = service.revise(command)
    assert not isinstance(first, GenerationFailureV1)
    assert first.replayed is False
    assert tracking.resolve_calls == 1
    assert len(provider.calls) == 1

    replay_tracking = _TrackingDefinitionResolver(inner, fail=True)
    replay_service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_other",
        definition_resolver=replay_tracking,
        revise_operations=rev_ops,
    )
    second = replay_service.revise(command)
    assert not isinstance(second, GenerationFailureV1)
    assert second.replayed is True
    assert second.candidate_id == first.candidate_id
    assert replay_tracking.resolve_calls == 0
    assert len(provider.calls) == 1


def test_revise_locator_changed_body_conflicts_before_resolver(load_fixture) -> None:
    from statblocks_v1.domain.errors import IdempotencyConflictError

    definition, persistence, locator = _revision_locator_setup(load_fixture)
    inner = PersistenceDefinitionResolver(persistence)
    provider = FakeDefinitionProvider(definition.model_dump(mode="json"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRevisionOperationRepository,
    )

    rev_ops = InMemoryCandidateRevisionOperationRepository(candidates, clock=lambda: now)
    command = ReviseStatblockCommandV1(
        request_id="req_locator_conflict",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Tighten the club damage"],
        caller=CallerProvenanceV1(caller_scope="tests"),
        source_locator=locator,
    )
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_locconflict1",
        definition_resolver=inner,
        revise_operations=rev_ops,
    )
    assert not isinstance(service.revise(command), GenerationFailureV1)
    assert len(provider.calls) == 1

    conflict_tracking = _TrackingDefinitionResolver(inner, fail=True)
    conflict_service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_other",
        definition_resolver=conflict_tracking,
        revise_operations=rev_ops,
    )
    with pytest.raises(IdempotencyConflictError):
        conflict_service.revise(
            ReviseStatblockCommandV1(
                request_id=command.request_id,
                ruleset=RulesetRef(system="dnd5e", edition="2024"),
                revision_instructions=["Totally different edit"],
                caller=CallerProvenanceV1(caller_scope="tests"),
                source_locator=ExactRevisionLocatorV1(
                    statblock_id="sb_other000001", revision_id="rev_other00001"
                ),
            )
        )
    assert conflict_tracking.resolve_calls == 0
    assert len(provider.calls) == 1


def test_revise_replay_through_fresh_service_instance(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    provider = FakeDefinitionProvider(source.model_dump(mode="json"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRevisionOperationRepository,
    )

    rev_ops = InMemoryCandidateRevisionOperationRepository(candidates, clock=lambda: now)
    gen_ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    command = _revise_command(source, revision_instructions=["Bump challenge slightly"])

    def build_service() -> GenerationServiceV1:
        return GenerationServiceV1(
            provider=provider,
            candidates=candidates,
            settings=GenerationSettingsV1("test-model", 1, 0, 60),
            clock=lambda: now,
            candidate_id_factory=lambda: "cand_freshrev1",
            generate_operations=gen_ops,
            revise_operations=rev_ops,
        )

    first = build_service().revise(command)
    second = build_service().revise(command)

    assert isinstance(first, GenerateOutcomeV1)
    assert isinstance(second, GenerateOutcomeV1)
    assert first.replayed is False
    assert second.replayed is True
    assert first.candidate_id == second.candidate_id == "cand_freshrev1"
    assert len(provider.calls) == 1


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


def _revise_command(source_definition, **overrides) -> ReviseStatblockCommandV1:
    base = dict(
        request_id="req_revision",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        revision_instructions=["Adjust the creature for testing."],
        caller=CallerProvenanceV1(caller_scope="tests", actor="unit"),
        source_definition=source_definition,
    )
    base.update(overrides)
    return ReviseStatblockCommandV1(**base)


def test_generate_replay_returns_same_candidate_without_provider(load_fixture) -> None:
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = _service(None, provider=provider)
    first = service.generate(_command())
    second = service.generate(_command())

    assert isinstance(first, GenerateOutcomeV1)
    assert isinstance(second, GenerateOutcomeV1)
    assert first.replayed is False
    assert second.replayed is True
    assert first.candidate_id == second.candidate_id == "cand_1"
    assert first.candidate.model_dump(mode="json") == second.candidate.model_dump(mode="json")
    assert len(provider.calls) == 1


def test_revise_replay_returns_same_candidate_without_provider(load_fixture) -> None:
    from statblocks_v1.domain.errors import IdempotencyConflictError

    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    provider = FakeDefinitionProvider(source.model_dump(mode="json"))
    service = _service(source.model_dump(mode="json"), provider=provider)
    command = _revise_command(source, revision_instructions=["Bump challenge slightly"])
    first = service.revise(command)
    second = service.revise(command)

    assert isinstance(first, GenerateOutcomeV1)
    assert isinstance(second, GenerateOutcomeV1)
    assert first.replayed is False
    assert second.replayed is True
    assert first.candidate_id == second.candidate_id == "cand_1"
    assert first.candidate.generation_receipt.request_digest is not None
    assert first.candidate.generation_receipt.request_digest.startswith("sha256:")
    assert len(provider.calls) == 1

    with pytest.raises(IdempotencyConflictError):
        service.revise(
            _revise_command(source, revision_instructions=["Different instructions"])
        )
    assert len(provider.calls) == 1


def test_revise_without_operations_repository_fails_closed(load_fixture) -> None:
    source = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))

    class TrackingProvider:
        provider_name = "track"

        def __init__(self) -> None:
            self.calls = 0

        def generate_definition(self, **kwargs):
            self.calls += 1
            raise AssertionError("provider must not be called without revise ops repo")

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
    )

    provider = TrackingProvider()
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_x",
        generate_operations=InMemoryCandidateGenerationOperationRepository(
            candidates, clock=lambda: now
        ),
        revise_operations=None,
    )
    result = service.revise(_revise_command(source))
    assert isinstance(result, GenerationFailureV1)
    assert result.kind == "persistence_unavailable"
    assert provider.calls == 0


def test_generate_changed_digest_conflicts_without_provider(load_fixture) -> None:
    from statblocks_v1.domain.errors import IdempotencyConflictError

    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = _service(None, provider=provider)
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    assert len(provider.calls) == 1

    with pytest.raises(IdempotencyConflictError):
        service.generate(
            _command(source=SourceSnapshotV1(name_hint="Bruiser", description="Changed intent."))
        )
    assert len(provider.calls) == 1


def test_generate_uses_pinned_identity_despite_command_mutation(load_fixture) -> None:
    """Idempotent generate must not re-read request_id/scope/digest from a mutated command."""

    command = _command()
    inner = FakeDefinitionProvider(load_fixture("simple_bruiser"))

    class MutatingProvider:
        provider_name = "mutating"

        def generate_definition(self, **kwargs):
            command.request_id = "hijacked_request"
            command.caller.caller_scope = "hijacked_scope"
            command.source.description = "Hijacked description after pin."
            return inner.generate_definition(**kwargs)

    service = _service(None, provider=MutatingProvider())
    result = service.generate(command)
    assert isinstance(result, GenerateOutcomeV1)
    assert result.candidate.generation_receipt is not None
    assert result.candidate.generation_receipt.request_id == "req_generation"
    assert result.candidate.generation_receipt.caller_scope == "tests"
    # Mutated command must not create a second operation under the hijacked key.
    assert service._generate_operations.get_generate_operation(  # type: ignore[union-attr]
        "hijacked_scope", "hijacked_request"
    ) is None
    assert service._generate_operations.get_generate_operation(  # type: ignore[union-attr]
        "tests", "req_generation"
    ) is not None


def test_generate_terminal_failure_replays_without_provider(load_fixture) -> None:
    provider = FakeDefinitionProvider(
        ProviderOutcomeV1(kind=ProviderOutcomeKind.refusal, message="nope")
    )
    service = _service(None, provider=provider)
    first = service.generate(_command())
    second = service.generate(_command())

    assert isinstance(first, GenerationFailureV1)
    assert isinstance(second, GenerationFailureV1)
    assert first.kind == second.kind == "provider_refusal"
    assert len(provider.calls) == 1


def test_generate_in_progress_when_lease_active(load_fixture) -> None:
    from datetime import timedelta

    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def clock():
        return now["t"]

    started = threading.Event()
    release = threading.Event()

    class BlockingProvider:
        provider_name = "blocking"

        def generate_definition(self, **kwargs):
            started.set()
            release.wait(timeout=2)
            return FakeDefinitionProvider(load_fixture("simple_bruiser")).generate_definition(
                **kwargs
            )

    candidates = InMemoryCandidateRepository(clock=clock)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=clock)
    service = GenerationServiceV1(
        provider=BlockingProvider(),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=clock,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )

    results: list = []

    def worker():
        results.append(service.generate(_command()))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(worker)
        assert started.wait(timeout=2)
        second = service.generate(_command())
        release.set()
        first.result(timeout=2)

    assert isinstance(second, GenerationFailureV1)
    assert second.kind == "generation_in_progress"
    assert isinstance(results[0], GenerateOutcomeV1)
    assert results[0].candidate_id == "cand_1"


def test_stale_worker_fail_does_not_echo_uncommitted_failure(load_fixture) -> None:
    from datetime import timedelta

    from statblocks_v1.application.repositories import compute_generate_candidate_digest
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationFailureSnapshotV1,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import ImmutableResourceConflictError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    ops._operations[("tests", "req_generation")] = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="active-owner",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=2,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ImmutableResourceConflictError):
        ops.fail_generate(
            caller_scope="tests",
            request_id="req_generation",
            request_digest=digest,
            lease_owner="stale-owner",
            failure=CandidateGenerationFailureSnapshotV1(
                kind="provider_refusal", message="stale local failure"
            ),
        )
    existing = ops.get_generate_operation("tests", "req_generation")
    assert existing is not None
    assert existing.status is CandidateGenerationStatusV1.pending
    assert existing.failure is None


def test_generate_expired_lease_takeover_retains_candidate_id(load_fixture) -> None:
    from datetime import timedelta

    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    # Seed an expired pending reservation for cand_reserved.
    ops._operations[("tests", "req_generation")] = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=__import__(
            "statblocks_v1.application.repositories", fromlist=["compute_generate_candidate_digest"]
        ).compute_generate_candidate_digest(_command()),
        candidate_id="cand_reserved",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="stale",
        lease_expires_at=now["t"] - timedelta(seconds=1),
        attempt_count=1,
        created_at=now["t"] - timedelta(seconds=10),
        updated_at=now["t"] - timedelta(seconds=10),
    )
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_should_not_use",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    result = service.generate(_command())
    assert isinstance(result, GenerateOutcomeV1)
    assert result.candidate_id == "cand_reserved"
    assert result.replayed is False
    assert len(provider.calls) == 1


def test_generate_replay_rejects_replaced_candidate_under_same_id(load_fixture) -> None:
    """Completed replay must fail closed when the candidate no longer binds to the op."""

    from datetime import timedelta

    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    assert first.candidate.generation_receipt is not None
    assert first.candidate.generation_receipt.request_digest is not None

    # Replace the durable candidate under the same ID with a digest-mismatched receipt.
    replaced = first.candidate.model_copy(
        deep=True,
        update={
            "generation_receipt": first.candidate.generation_receipt.model_copy(
                update={"request_digest": "sha256:" + ("e" * 64)}
            )
        },
    )
    candidates._candidates["cand_1"] = replaced
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())
    assert len(provider.calls) == 1


def test_stale_worker_complete_convergence_is_observed_as_replay(load_fixture) -> None:
    """Service must treat complete_generate(already_completed=True) as replay, not fresh persist."""

    from statblocks_v1.application.repositories import GenerateCompleteResult
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    real_ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)

    class ConvergenceOps:
        """Adapter that surfaces race-convergence as already_completed=True."""

        def get_generate_operation(self, caller_scope: str, request_id: str):
            return real_ops.get_generate_operation(caller_scope, request_id)

        def begin_generate(self, **kwargs):
            return real_ops.begin_generate(**kwargs)

        def fail_generate(self, **kwargs):
            return real_ops.fail_generate(**kwargs)

        def complete_generate(self, **kwargs):
            result = real_ops.complete_generate(**kwargs)
            # Simulate discovering another worker already completed this operation.
            return GenerateCompleteResult(
                candidate=result.candidate, already_completed=True
            )

    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ConvergenceOps(),
        generate_lease_seconds=120,
    )
    result = service.generate(_command())
    assert isinstance(result, GenerateOutcomeV1)
    assert result.replayed is True
    assert len(provider.calls) == 1


def test_generate_expired_candidate_replay_raises_410(load_fixture) -> None:
    from datetime import timedelta

    from statblocks_v1.domain.errors import CandidateExpiredError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 5),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    now["t"] = now["t"] + timedelta(seconds=10)
    with pytest.raises(CandidateExpiredError) as exc:
        service.generate(_command())
    assert exc.value.details["candidate_id"] == "cand_1"


def test_generate_premature_candidate_loss_is_integrity_failure(load_fixture) -> None:
    from statblocks_v1.domain.errors import CandidateMissingBeforeExpiryError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    del candidates._candidates["cand_1"]
    with pytest.raises(CandidateMissingBeforeExpiryError) as exc:
        service.generate(_command())
    assert exc.value.details["candidate_id"] == "cand_1"
    assert len(provider.calls) == 1


def test_different_request_ids_are_independent(load_fixture) -> None:
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = _service(None, provider=provider)
    first = service.generate(_command(request_id="req_a"))
    second = service.generate(_command(request_id="req_b"))
    assert isinstance(first, GenerateOutcomeV1)
    assert isinstance(second, GenerateOutcomeV1)
    assert first.candidate_id != second.candidate_id
    assert len(provider.calls) == 2


def test_replay_foreign_candidate_earlier_expiry_is_integrity_not_410(
    load_fixture,
) -> None:
    """Foreign/replaced candidate TTL must not masquerade as ordinary expiry."""

    from datetime import timedelta

    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(
        candidates, clock=lambda: now["t"]
    )
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    assert first.candidate.generation_receipt is not None

    # Replace with a foreign document whose own expires_at is already past.
    foreign = first.candidate.model_copy(
        deep=True,
        update={
            "expires_at": now["t"] - timedelta(seconds=1),
            "generation_receipt": first.candidate.generation_receipt.model_copy(
                update={
                    "request_id": "req_foreign",
                    "request_digest": "sha256:" + ("a" * 64),
                }
            ),
        },
    )
    candidates._candidates["cand_1"] = foreign
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())
    assert len(provider.calls) == 1


def test_replay_respects_operation_expiry_over_extended_candidate_ttl(
    load_fixture,
) -> None:
    """Extended candidate expires_at disagrees with the operation → integrity, not success."""

    from datetime import timedelta

    from statblocks_v1.domain.errors import (
        CandidateExpiredError,
        GenerateOperationIntegrityError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(
        candidates, clock=lambda: now["t"]
    )
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)

    # Document TTL extended past the operation-recorded expiry.
    extended = first.candidate.model_copy(
        update={"expires_at": now["t"] + timedelta(hours=24)}
    )
    candidates._candidates["cand_1"] = extended
    now["t"] = now["t"] + timedelta(seconds=120)
    with pytest.raises(GenerateOperationIntegrityError):
        try:
            service.generate(_command())
        except CandidateExpiredError as expired:
            raise AssertionError(
                "extended candidate TTL mismatch must not become 410"
            ) from expired
    assert len(provider.calls) == 1


def test_terminal_race_mismatched_reserved_candidate_id_fails_closed(
    load_fixture,
) -> None:
    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import (
        GenerateOperationIntegrityError,
        ImmutableResourceConflictError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_reserved",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    terminal = claimed.model_copy(
        update={
            "candidate_id": "cand_other",
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": now + timedelta(minutes=5),
            "outcome_digest": "sha256:" + ("a" * 64),
        }
    )

    class RaceOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return terminal

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            raise ImmutableResourceConflictError("candidate", "cand_reserved")

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_reserved",
        generate_operations=RaceOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())


def test_terminal_race_mismatched_request_digest_fails_closed(load_fixture) -> None:
    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import (
        GenerateOperationIntegrityError,
        ImmutableResourceConflictError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    terminal = claimed.model_copy(
        update={
            "request_digest": "sha256:" + ("f" * 64),
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": now + timedelta(minutes=5),
            "outcome_digest": "sha256:" + ("a" * 64),
        }
    )

    class RaceOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return terminal

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            raise ImmutableResourceConflictError("candidate", "cand_1")

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=RaceOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())


def test_fail_generate_indeterminate_recovers_concurrent_completed_candidate(
    load_fixture,
) -> None:
    """Indeterminate fail write must return concurrent success, not persistence_unavailable."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        compute_candidate_outcome_digest,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.application.provider import ProviderOutcomeKind, ProviderOutcomeV1
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import TransactionIndeterminateError
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.resources import (
        STATBLOCK_CONTRACT,
        STATBLOCK_CONTRACT_VERSION,
        GeneratedStatblockCandidateV1,
        GenerationReceiptV1,
    )
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
    from statblocks_v1.domain.validation import validate_definition
    from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    stored = GeneratedStatblockCandidateV1(
        candidate_id="cand_1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt=GenerationReceiptV1(
            request_id="req_generation",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="tests",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(stored)
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-fail",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    terminal = claimed.model_copy(
        update={
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": stored.expires_at,
            "outcome_digest": compute_candidate_outcome_digest(stored),
        }
    )

    class IndeterminateFailOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return terminal

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise TransactionIndeterminateError()

        def complete_generate(self, **kwargs):
            raise AssertionError("complete_generate should not be called")

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(
            ProviderOutcomeV1(kind=ProviderOutcomeKind.refusal, message="nope")
        ),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=IndeterminateFailOps(),
        generate_lease_seconds=120,
    )
    result = service.generate(_command())
    assert isinstance(result, GenerateOutcomeV1)
    assert result.candidate_id == "cand_1"
    assert result.replayed is True


def test_generate_replay_rejects_altered_mechanics_same_receipt(load_fixture) -> None:
    """Completed replay must fail closed when mechanics change under the same receipt."""

    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.validation import validate_definition
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now["t"])
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)

    altered_definition = first.candidate.definition.model_copy(
        update={
            "identity": first.candidate.definition.identity.model_copy(
                update={"name": "Altered Brute"}
            )
        }
    )
    replaced = first.candidate.model_copy(
        update={
            "definition": altered_definition,
            "validation_receipt": validate_definition(
                altered_definition, ValidationMode.generation_candidate
            ),
        }
    )
    candidates._candidates["cand_1"] = replaced
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())
    assert len(provider.calls) == 1


def test_complete_path_respects_operation_expiry_when_candidate_retained(
    load_fixture,
) -> None:
    """complete_generate success must not return a candidate past operation expiry."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        GenerateCompleteResult,
        compute_candidate_outcome_digest,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import CandidateExpiredError
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.resources import (
        STATBLOCK_CONTRACT,
        STATBLOCK_CONTRACT_VERSION,
        GeneratedStatblockCandidateV1,
        GenerationReceiptV1,
    )
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
    from statblocks_v1.domain.validation import validate_definition
    from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    digest = compute_generate_candidate_digest(_command())
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    retained = GeneratedStatblockCandidateV1(
        candidate_id="cand_1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt=GenerationReceiptV1(
            request_id="req_generation",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now["t"],
            caller_scope="tests",
            request_digest=digest,
        ),
        created_at=now["t"],
        expires_at=now["t"] - timedelta(seconds=1),
    )
    candidates._create_unlocked(retained)
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now["t"] + timedelta(seconds=60),
        attempt_count=1,
        created_at=now["t"],
        updated_at=now["t"],
    )
    terminal = claimed.model_copy(
        update={
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now["t"],
            "candidate_expires_at": retained.expires_at,
            "outcome_digest": compute_candidate_outcome_digest(retained),
        }
    )

    class ExpiredCompleteOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return terminal

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            return GenerateCompleteResult(candidate=retained, already_completed=True)

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ExpiredCompleteOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(CandidateExpiredError) as exc:
        service.generate(_command())
    assert exc.value.details["candidate_id"] == "cand_1"


def test_complete_path_missing_candidate_before_expiry_is_premature_loss(
    load_fixture,
) -> None:
    """Missing completed candidate with future op expiry must not be persistence_unavailable."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import (
        CandidateMissingBeforeExpiryError,
        PersistenceUnavailableError,
    )
    from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    terminal = claimed.model_copy(
        update={
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": now + timedelta(minutes=5),
            "outcome_digest": "sha256:" + ("a" * 64),
        }
    )

    class MissingCompleteOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return terminal

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            raise PersistenceUnavailableError()

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=MissingCompleteOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(CandidateMissingBeforeExpiryError) as exc:
        service.generate(_command())
    assert exc.value.details["candidate_id"] == "cand_1"


def test_complete_path_redirected_completed_record_fails_closed(load_fixture) -> None:
    """Success reread after complete must bind reserved candidate_id and digest."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        GenerateCompleteResult,
        compute_candidate_outcome_digest,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.resources import (
        STATBLOCK_CONTRACT,
        STATBLOCK_CONTRACT_VERSION,
        GeneratedStatblockCandidateV1,
        GenerationReceiptV1,
    )
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
    from statblocks_v1.domain.validation import validate_definition
    from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    retained = GeneratedStatblockCandidateV1(
        candidate_id="cand_other",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt=GenerationReceiptV1(
            request_id="req_generation",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="tests",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(retained)
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    redirected = claimed.model_copy(
        update={
            "candidate_id": "cand_other",
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": retained.expires_at,
            "outcome_digest": compute_candidate_outcome_digest(retained),
        }
    )

    class RedirectedCompleteOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return redirected

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            return GenerateCompleteResult(candidate=retained, already_completed=True)

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=RedirectedCompleteOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())


def test_complete_path_corrupted_digest_after_complete_fails_closed(load_fixture) -> None:
    """Success reread after complete must reject a swapped request_digest."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import (
        GenerateBeginClaimed,
        GenerateCompleteResult,
        compute_candidate_outcome_digest,
        compute_generate_candidate_digest,
    )
    from statblocks_v1.domain.candidate_operations import (
        GENERATE_CANDIDATE_OPERATION,
        CandidateGenerationOperationV1,
        CandidateGenerationStatusV1,
    )
    from statblocks_v1.domain.errors import GenerateOperationIntegrityError
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.resources import (
        STATBLOCK_CONTRACT,
        STATBLOCK_CONTRACT_VERSION,
        GeneratedStatblockCandidateV1,
        GenerationReceiptV1,
    )
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
    from statblocks_v1.domain.validation import validate_definition
    from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    digest = compute_generate_candidate_digest(_command())
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    receipt = validate_definition(definition, ValidationMode.generation_candidate)
    retained = GeneratedStatblockCandidateV1(
        candidate_id="cand_1",
        contract=STATBLOCK_CONTRACT,
        contract_version=STATBLOCK_CONTRACT_VERSION,
        definition=definition,
        validation_receipt=receipt,
        generation_receipt=GenerationReceiptV1(
            request_id="req_generation",
            provider="test",
            model="test-model",
            prompt_version="v1",
            schema_version="v1",
            schema_fingerprint="fp",
            generated_at=now,
            caller_scope="tests",
            request_digest=digest,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=5),
    )
    candidates._create_unlocked(retained)
    claimed = CandidateGenerationOperationV1(
        caller_scope="tests",
        operation=GENERATE_CANDIDATE_OPERATION,
        request_id="req_generation",
        request_digest=digest,
        candidate_id="cand_1",
        status=CandidateGenerationStatusV1.pending,
        lease_owner="worker-a",
        lease_expires_at=now + timedelta(seconds=60),
        attempt_count=1,
        created_at=now,
        updated_at=now,
    )
    corrupted = claimed.model_copy(
        update={
            "request_digest": "sha256:" + ("f" * 64),
            "status": CandidateGenerationStatusV1.completed,
            "completed_at": now,
            "candidate_expires_at": retained.expires_at,
            "outcome_digest": compute_candidate_outcome_digest(retained),
        }
    )

    class CorruptedDigestOps:
        def get_generate_operation(self, caller_scope: str, request_id: str):
            return corrupted

        def begin_generate(self, **kwargs):
            return GenerateBeginClaimed(operation=claimed)

        def fail_generate(self, **kwargs):
            raise AssertionError("fail_generate should not be called")

        def complete_generate(self, **kwargs):
            return GenerateCompleteResult(candidate=retained, already_completed=True)

    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=CorruptedDigestOps(),
        generate_lease_seconds=120,
    )
    with pytest.raises(GenerateOperationIntegrityError):
        service.generate(_command())


def test_replay_mismatched_operation_and_candidate_expiry_fails_closed(
    load_fixture,
) -> None:
    """Op vs candidate expires_at disagreement is integrity failure, not 410/success."""

    from datetime import timedelta

    from statblocks_v1.application.repositories import compute_candidate_outcome_digest
    from statblocks_v1.domain.errors import (
        CandidateExpiredError,
        GenerateOperationIntegrityError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candidates = InMemoryCandidateRepository(clock=lambda: now)
    ops = InMemoryCandidateGenerationOperationRepository(candidates, clock=lambda: now)
    service = GenerationServiceV1(
        provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 3600),
        clock=lambda: now,
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)

    key = ("tests", "req_generation")
    existing = ops._operations[key]
    mismatched_expiry = existing.candidate_expires_at + timedelta(hours=1)
    # Keep outcome_digest aligned with the live candidate so only expiry fields diverge.
    ops._operations[key] = existing.model_copy(
        update={
            "candidate_expires_at": mismatched_expiry,
            "outcome_digest": compute_candidate_outcome_digest(first.candidate),
        }
    )
    with pytest.raises(GenerateOperationIntegrityError) as exc:
        service.generate(_command())
    reason = exc.value.details.get("reason") or exc.value.message
    assert "expires_at" in reason
    # Must not surface as ordinary expiry when both timestamps are still in the future.
    with pytest.raises(GenerateOperationIntegrityError):
        try:
            service.generate(_command())
        except CandidateExpiredError as expired:
            raise AssertionError("expiry mismatch must not become 410") from expired


def test_replay_past_op_expiry_with_later_candidate_expiry_is_integrity(
    load_fixture,
) -> None:
    """Corrupted past op expiry must not 410 when retained candidate still agrees later.

    Candidate expires at 12:00; operation corrupted to 11:00; replay at 11:30.
    Present candidate with disagreeing expiry → integrity, not ordinary 410.
    """

    from statblocks_v1.application.repositories import compute_candidate_outcome_digest
    from statblocks_v1.domain.errors import (
        CandidateExpiredError,
        GenerateOperationIntegrityError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(
        candidates, clock=lambda: now["t"]
    )
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    # TTL 2h → candidate.expires_at = 12:00 when created at 10:00.
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 7200),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    assert first.candidate.expires_at == datetime(
        2026, 1, 1, 12, 0, tzinfo=timezone.utc
    )

    key = ("tests", "req_generation")
    existing = ops._operations[key]
    # Corrupt operation expiry to 11:00 while candidate remains at 12:00.
    corrupted_op_expiry = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    ops._operations[key] = existing.model_copy(
        update={
            "candidate_expires_at": corrupted_op_expiry,
            "outcome_digest": compute_candidate_outcome_digest(first.candidate),
        }
    )
    # Replay at 11:30: op expiry past, candidate still present and unexpired.
    now["t"] = datetime(2026, 1, 1, 11, 30, tzinfo=timezone.utc)
    with pytest.raises(GenerateOperationIntegrityError) as exc:
        try:
            service.generate(_command())
        except CandidateExpiredError as expired:
            raise AssertionError(
                "past op expiry with later candidate expiry must not become 410"
            ) from expired
    reason = exc.value.details.get("reason") or exc.value.message
    assert "expires_at" in reason
    assert len(provider.calls) == 1


def test_replay_missing_candidate_after_op_expiry_raises_410(load_fixture) -> None:
    """Missing candidate with past operation expiry is ordinary 410, not premature loss."""

    from datetime import timedelta

    from statblocks_v1.domain.errors import (
        CandidateExpiredError,
        CandidateMissingBeforeExpiryError,
    )
    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateGenerationOperationRepository,
        InMemoryCandidateRepository,
    )

    now = {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    candidates = InMemoryCandidateRepository(clock=lambda: now["t"])
    ops = InMemoryCandidateGenerationOperationRepository(
        candidates, clock=lambda: now["t"]
    )
    provider = FakeDefinitionProvider(load_fixture("simple_bruiser"))
    service = GenerationServiceV1(
        provider=provider,
        candidates=candidates,
        settings=GenerationSettingsV1("test-model", 1, 0, 60),
        clock=lambda: now["t"],
        candidate_id_factory=lambda: "cand_1",
        generate_operations=ops,
        generate_lease_seconds=120,
    )
    first = service.generate(_command())
    assert isinstance(first, GenerateOutcomeV1)
    del candidates._candidates["cand_1"]
    now["t"] = now["t"] + timedelta(seconds=120)
    with pytest.raises(CandidateExpiredError) as exc:
        try:
            service.generate(_command())
        except CandidateMissingBeforeExpiryError as missing:
            raise AssertionError(
                "missing candidate after op expiry must be 410, not premature loss"
            ) from missing
    assert exc.value.details["candidate_id"] == "cand_1"
    assert len(provider.calls) == 1
