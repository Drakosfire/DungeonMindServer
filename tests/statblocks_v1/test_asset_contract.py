from __future__ import annotations

import json
from datetime import datetime, timezone

from statblocks_v1.application.assets import AssetGateway
from statblocks_v1.application.commands import AssetOptionsV1
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.assets import AssetBindingV1, AssetBriefV1, AssetRefV1
from statblocks_v1.domain.digests import compute_definition_digest
from statblocks_v1.domain.resources import AssetWarningCode
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.infrastructure.fake_asset_gateway import FakeAssetGateway
from statblocks_v1.infrastructure.fake_provider import FakeDefinitionProvider
from statblocks_v1.infrastructure.memory_repositories import InMemoryCandidateRepository


def _asset() -> AssetRefV1:
    return AssetRefV1(
        asset_id="asset_123",
        provider_kind="cloudflare_images",
        url="https://imagedelivery.net/account/asset_123/public",
        mime_type="image/png",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_asset_binding_is_typed_and_outside_mechanics_digest(load_fixture) -> None:
    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    digest = compute_definition_digest(definition)
    binding = AssetBindingV1(asset=_asset(), role="portrait")

    assert binding.asset.asset_id == "asset_123"
    assert compute_definition_digest(definition) == digest


def test_asset_gateway_populates_refs_and_failure_warns(load_fixture) -> None:
    from statblocks_v1.application.commands import (
        CallerProvenanceV1,
        GenerateStatblockCommandV1,
        SourceSnapshotV1,
    )
    from statblocks_v1.domain.profiles import RulesetRef

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    command = GenerateStatblockCommandV1(
        request_id="asset-contract",
        ruleset=RulesetRef(system="dnd5e", edition="2024"),
        source=SourceSnapshotV1(name_hint="Bruiser", description="A brutal enforcer."),
        asset_options=AssetOptionsV1(generate_images=True),
        caller=CallerProvenanceV1(caller_scope="tests"),
    )

    def generate(gateway: AssetGateway):
        return GenerationServiceV1(
            provider=FakeDefinitionProvider(load_fixture("simple_bruiser")),
            candidates=InMemoryCandidateRepository(clock=lambda: now),
            settings=GenerationSettingsV1("test-model", 1, 0, 60),
            clock=lambda: now,
            candidate_id_factory=lambda: "cand_asset",
            asset_gateway=gateway,
        ).generate(command)

    generated = generate(FakeAssetGateway([_asset()]))
    warning = generate(FakeAssetGateway(error=RuntimeError("pipeline unavailable")))

    assert generated.assets == [_asset()]
    assert generated.asset_brief == AssetBriefV1(prompt="A brutal enforcer.")
    assert warning.assets == []
    assert [w.code for w in warning.asset_warnings] == [
        AssetWarningCode.asset_generation_failed
    ]
    assert warning.asset_warnings[0].message.startswith("Asset generation failed")
