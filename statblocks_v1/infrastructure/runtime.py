"""Production dependency construction for the statblock v1 outer boundary.

Callers outside the package (``app.py``) supply the Firestore client and optional
asset pipeline so this layer never imports repository-owned ``firestore`` /
``cloudflare`` packages directly.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from statblocks_v1.application.assets import AssetGateway
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.repositories import (
    CandidateRepository,
    StatblockPersistenceRepository,
)
from statblocks_v1.application.resolvers import PersistenceDefinitionResolver
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.config import ConfigurationError, StatblocksV1Settings
from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1
from statblocks_v1.domain.errors import InternalServiceMisconfiguredError, PersistenceUnavailableError
from statblocks_v1.infrastructure.cloudflare_asset_gateway import (
    CloudflareAssetGateway,
    PipelineGenerate,
)
from statblocks_v1.infrastructure.firestore_repositories import (
    FirestoreCandidateRepository,
    FirestoreStatblockPersistenceRepository,
)
from statblocks_v1.infrastructure.openai_provider import OpenAIDefinitionProvider

logger = logging.getLogger("statblocks_v1")


def apply_logging_settings(settings: StatblocksV1Settings) -> None:
    """Apply configured log level to the v1 logger (never logs secret values)."""
    level = getattr(logging, settings.log_level, logging.INFO)
    logger.setLevel(level)
    if settings.structured_logging and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)


def _require_firestore(settings: StatblocksV1Settings) -> None:
    if not settings.firestore_enabled:
        raise PersistenceUnavailableError()


class _TimeoutAssetGateway:
    """Enforces STATBLOCKS_V1_ASSET_TIMEOUT_SECONDS around the injected pipeline."""

    def __init__(self, inner: AssetGateway, timeout_seconds: float) -> None:
        self._inner = inner
        self._timeout_seconds = timeout_seconds

    def generate(self, brief: AssetBriefV1) -> list[AssetRefV1]:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._inner.generate, brief)
            try:
                return future.result(timeout=self._timeout_seconds)
            except FuturesTimeout as error:
                raise TimeoutError(
                    f"asset generation exceeded {self._timeout_seconds}s"
                ) from error


def build_asset_gateway(
    settings: StatblocksV1Settings | None = None,
    *,
    pipeline: PipelineGenerate | None = None,
) -> AssetGateway | None:
    """Return a gateway only when assets are enabled and a pipeline is supplied."""
    settings = settings or StatblocksV1Settings.from_environment()
    if not settings.asset_gateway_enabled:
        return None
    if pipeline is None:
        raise ConfigurationError(
            "STATBLOCKS_V1_ASSET_GATEWAY_ENABLED requires an injected asset pipeline"
        )
    return _TimeoutAssetGateway(
        CloudflareAssetGateway(pipeline),
        settings.asset_timeout_seconds,
    )


def build_candidate_repository(client: Any) -> CandidateRepository:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    _require_firestore(settings)
    if client is None:
        raise InternalServiceMisconfiguredError("Firestore client is not configured")
    return FirestoreCandidateRepository(
        client,
        candidates_collection=settings.candidates_collection,
        idempotency_collection=settings.idempotency_collection,
    )


def build_persistence_repository(client: Any) -> StatblockPersistenceRepository:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    _require_firestore(settings)
    if client is None:
        raise InternalServiceMisconfiguredError("Firestore client is not configured")
    return FirestoreStatblockPersistenceRepository(
        client,
        statblocks_collection=settings.statblocks_collection,
        idempotency_collection=settings.idempotency_collection,
    )


def build_generation_service(
    *,
    client: Any | None = None,
    candidates: CandidateRepository | None = None,
    persistence: StatblockPersistenceRepository | None = None,
    asset_pipeline: PipelineGenerate | None = None,
    provider: Any | None = None,
) -> GenerationServiceV1:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    candidate_repo = candidates or build_candidate_repository(client)
    persistence_repo = persistence or build_persistence_repository(client)
    asset_gateway = build_asset_gateway(settings, pipeline=asset_pipeline)
    return GenerationServiceV1(
        provider=provider if provider is not None else OpenAIDefinitionProvider(),
        candidates=candidate_repo,
        settings=GenerationSettingsV1(
            model=settings.model,
            timeout_seconds=settings.provider_timeout_seconds,
            max_retries=settings.provider_max_retries,
            candidate_ttl_seconds=settings.candidate_ttl_seconds,
        ),
        definition_resolver=PersistenceDefinitionResolver(persistence_repo),
        asset_gateway=asset_gateway,
    )


def probe_production_composition(
    settings: StatblocksV1Settings,
    *,
    client: Any | None = None,
    factories_configured: bool = False,
) -> list[str]:
    """Non-invasive readiness probe used by the readiness route and composition tests."""
    errors: list[str] = []
    if settings.firestore_enabled and client is None and not factories_configured:
        errors.append("firestore_client_unconfigured")
    if settings.asset_gateway_enabled:
        try:
            build_asset_gateway(settings, pipeline=None)
        except ConfigurationError:
            errors.append("asset_gateway_pipeline_unconfigured")
    return errors
