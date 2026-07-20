"""Production composition proofs with fake external clients (not the isolated lane alone)."""
from __future__ import annotations

import logging

import pytest

from statblocks_v1.application.composition_state import set_asset_pipeline_ready
from statblocks_v1.config import StatblocksV1Settings
from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1
from statblocks_v1.domain.errors import (
    InternalServiceMisconfiguredError,
    PersistenceUnavailableError,
)
from statblocks_v1.infrastructure.runtime import (
    apply_logging_settings,
    build_asset_gateway,
    build_candidate_repository,
    build_generation_service,
    build_persistence_repository,
    configure_asset_pipeline,
    probe_production_composition,
)


class _FakeFirestore:
    def collection(self, name: str):
        raise AssertionError(f"unexpected firestore call for {name}")


def test_firestore_disabled_blocks_repository_construction(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_FIRESTORE_ENABLED", "false")
    with pytest.raises(PersistenceUnavailableError):
        build_candidate_repository(_FakeFirestore())
    with pytest.raises(PersistenceUnavailableError):
        build_persistence_repository(_FakeFirestore())


def test_asset_gateway_wired_only_when_enabled_with_pipeline(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "false")
    assert build_asset_gateway() is None

    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "true")
    configure_asset_pipeline(None)
    with pytest.raises(InternalServiceMisconfiguredError):
        build_asset_gateway()

    from datetime import datetime, timezone

    def pipeline(brief: AssetBriefV1) -> list[AssetRefV1]:
        return [
            AssetRefV1(
                asset_id="img_1",
                provider_kind="cloudflare_images",
                url="https://cdn.example/img_1.png",
                mime_type="image/png",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]

    gateway = build_asset_gateway(pipeline=pipeline)
    assert gateway is not None
    refs = gateway.generate(AssetBriefV1(prompt="portrait"))
    assert refs[0].asset_id == "img_1"

def test_generation_service_uses_settings_and_optional_assets(monkeypatch) -> None:
    class DummyProvider:
        provider_name = "dummy"

        def generate_definition(self, **kwargs):
            raise AssertionError("not called")

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_OPENAI_MODEL", "test-model")
    monkeypatch.setenv("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("STATBLOCKS_V1_OPENAI_MAX_RETRIES", "2")
    monkeypatch.setenv("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", "30")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "true")

    from statblocks_v1.infrastructure.memory_repositories import (
        InMemoryCandidateRepository,
        InMemoryStatblockPersistenceRepository,
    )

    def pipeline(brief: AssetBriefV1) -> list[AssetRefV1]:
        return []

    provider = DummyProvider()
    service = build_generation_service(
        candidates=InMemoryCandidateRepository(),
        persistence=InMemoryStatblockPersistenceRepository(),
        asset_pipeline=pipeline,
        provider=provider,
    )
    assert service._settings.model == "test-model"
    assert service._settings.timeout_seconds == 12.0
    assert service._settings.max_retries == 2
    assert service._settings.candidate_ttl_seconds == 30
    assert service._asset_gateway is not None
    assert service._provider is provider


def test_logging_settings_applied(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_LOG_LEVEL", "WARNING")
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    assert logging.getLogger("statblocks_v1").level == logging.WARNING


def test_composition_probe_reports_missing_asset_pipeline(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "true")
    set_asset_pipeline_ready(False)
    settings = StatblocksV1Settings.from_environment()
    assert "asset_gateway_pipeline_unconfigured" in probe_production_composition(
        settings, client=object(), factories_configured=True
    )


def test_credentials_gate_keeps_pipeline_unconfigured_without_secrets(monkeypatch) -> None:
    from statblocks_v1.infrastructure.production_asset_pipeline import (
        production_asset_credentials_ready,
    )

    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_IMAGES_API_TOKEN", raising=False)
    assert production_asset_credentials_ready() is False



def test_asset_timeout_does_not_block_on_hung_pipeline(monkeypatch) -> None:
    import time

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "true")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_TIMEOUT_SECONDS", "0.05")

    def hung(_brief: AssetBriefV1) -> list[AssetRefV1]:
        time.sleep(2)
        return []

    gateway = build_asset_gateway(pipeline=hung)
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        gateway.generate(AssetBriefV1(prompt="https://example.com/x.png"))
    assert time.monotonic() - started < 1.0


def test_logging_disabled_stops_telemetry(monkeypatch, caplog) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai")
    monkeypatch.setenv("STATBLOCKS_V1_STRUCTURED_LOGGING", "false")
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    logger = logging.getLogger("statblocks_v1")
    assert logger.propagate is False
    assert logger.handlers == []
    with caplog.at_level(logging.INFO):
        logger.info("should_not_propagate")
    assert "should_not_propagate" not in caplog.text
