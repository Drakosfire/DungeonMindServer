"""Production dependency construction for the statblock v1 outer boundary.

Callers outside the package (``app.py``) supply the Firestore client and optional
asset pipeline so this layer never imports repository-owned ``firestore`` /
``cloudflare`` packages directly — except the dedicated production asset adapter.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

from statblocks_v1.application.composition_state import (
    asset_pipeline_ready as asset_pipeline_configured,
    set_asset_pipeline_ready,
)
from statblocks_v1.application.assets import AssetGateway
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.repositories import (
    CandidateRepository,
    StatblockPersistenceRepository,
)
from statblocks_v1.application.resolvers import PersistenceDefinitionResolver
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.config import StatblocksV1Settings
from statblocks_v1.domain.assets import AssetBriefV1, AssetRefV1
from statblocks_v1.domain.errors import InternalServiceMisconfiguredError, PersistenceUnavailableError
from statblocks_v1.infrastructure.cloudflare_asset_gateway import (
    CloudflareAssetGateway,
    PipelineGenerate,
)
from statblocks_v1.infrastructure.firestore_repositories import (
    FirestoreCandidateGenerationOperationRepository,
    FirestoreCandidateRevisionOperationRepository,
    FirestoreCandidateRepository,
    FirestoreStatblockPersistenceRepository,
)
from statblocks_v1.infrastructure.ge_provider import GenerationEngineDefinitionProvider
from statblocks_v1.observability import apply_telemetry_settings

logger = logging.getLogger("statblocks_v1")

# Shared pool so timeouts do not join a hung worker on context exit.
_ASSET_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="statblocks-v1-asset")

_asset_pipeline: PipelineGenerate | None = None


def configure_asset_pipeline(pipeline: PipelineGenerate | None) -> None:
    """Record whether production composition injected an asset pipeline."""
    global _asset_pipeline
    _asset_pipeline = pipeline
    set_asset_pipeline_ready(pipeline is not None)


def apply_logging_settings(settings: StatblocksV1Settings) -> None:
    """Apply configured log level and structured-logging policy."""
    apply_telemetry_settings(settings.structured_logging, settings.log_level)


def _require_firestore(settings: StatblocksV1Settings) -> None:
    if not settings.firestore_enabled:
        raise PersistenceUnavailableError()


class _TimeoutAssetGateway:
    """Enforces asset timeout without joining a hung worker on return."""

    def __init__(self, inner: AssetGateway, timeout_seconds: float) -> None:
        self._inner = inner
        self._timeout_seconds = timeout_seconds

    def generate(self, brief: AssetBriefV1) -> list[AssetRefV1]:
        future = _ASSET_EXECUTOR.submit(self._inner.generate, brief)
        try:
            return future.result(timeout=self._timeout_seconds)
        except FuturesTimeout as error:
            # Do not wait for the worker; abandon the future and fail the asset path.
            future.cancel()
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
    effective = pipeline if pipeline is not None else _asset_pipeline
    if effective is None:
        raise InternalServiceMisconfiguredError(
            "Statblock asset gateway is enabled but no pipeline is configured"
        )
    return _TimeoutAssetGateway(
        CloudflareAssetGateway(effective),
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


def build_generate_operation_repository(client: Any) -> FirestoreCandidateGenerationOperationRepository:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    _require_firestore(settings)
    if client is None:
        raise InternalServiceMisconfiguredError("Firestore client is not configured")
    return FirestoreCandidateGenerationOperationRepository(
        client,
        candidates_collection=settings.candidates_collection,
        generate_ops_collection=settings.generate_ops_collection,
    )


def build_revise_operation_repository(client: Any) -> FirestoreCandidateRevisionOperationRepository:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    _require_firestore(settings)
    if client is None:
        raise InternalServiceMisconfiguredError("Firestore client is not configured")
    return FirestoreCandidateRevisionOperationRepository(
        client,
        candidates_collection=settings.candidates_collection,
        revise_ops_collection=settings.revise_ops_collection,
    )


def build_generation_service(
    *,
    client: Any | None = None,
    candidates: CandidateRepository | None = None,
    persistence: StatblockPersistenceRepository | None = None,
    generate_operations: Any | None = None,
    revise_operations: Any | None = None,
    asset_pipeline: PipelineGenerate | None = None,
    provider: Any | None = None,
) -> GenerationServiceV1:
    settings = StatblocksV1Settings.from_environment()
    apply_logging_settings(settings)
    if asset_pipeline is not None:
        configure_asset_pipeline(asset_pipeline)
    candidate_repo = candidates or build_candidate_repository(client)
    persistence_repo = persistence or build_persistence_repository(client)
    generate_ops = generate_operations
    if generate_ops is None and client is not None:
        generate_ops = build_generate_operation_repository(client)
    if generate_ops is None:
        raise InternalServiceMisconfiguredError(
            "Candidate generate-operation repository is not configured"
        )
    revise_ops = revise_operations
    if revise_ops is None and client is not None:
        revise_ops = build_revise_operation_repository(client)
    if revise_ops is None:
        raise InternalServiceMisconfiguredError(
            "Candidate revise-operation repository is not configured"
        )
    try:
        asset_gateway = build_asset_gateway(settings, pipeline=asset_pipeline)
    except InternalServiceMisconfiguredError:
        raise
    return GenerationServiceV1(
        provider=provider if provider is not None else GenerationEngineDefinitionProvider(),
        candidates=candidate_repo,
        settings=GenerationSettingsV1(
            model=settings.model,
            timeout_seconds=settings.provider_timeout_seconds,
            max_retries=settings.provider_max_retries,
            candidate_ttl_seconds=settings.candidate_ttl_seconds,
        ),
        definition_resolver=PersistenceDefinitionResolver(persistence_repo),
        asset_gateway=asset_gateway,
        generate_operations=generate_ops,
        revise_operations=revise_ops,
        generate_lease_seconds=settings.generate_lease_seconds,
        revise_lease_seconds=settings.revise_lease_seconds,
    )


def probe_production_composition(
    settings: StatblocksV1Settings,
    *,
    client: Any | None = None,
    factories_configured: bool = False,
    asset_pipeline_ready_flag: bool | None = None,
) -> list[str]:
    """Non-invasive readiness probe used by the readiness route and composition tests."""
    errors: list[str] = []
    if settings.firestore_enabled and client is None and not factories_configured:
        errors.append("firestore_client_unconfigured")
    if settings.asset_gateway_enabled:
        ready = (
            asset_pipeline_configured()
            if asset_pipeline_ready_flag is None
            else asset_pipeline_ready_flag
        )
        if not ready:
            errors.append("asset_gateway_pipeline_unconfigured")
    if settings.feature_enabled and settings.openai_api_key and not settings.firestore_enabled:
        errors.append("generation_requires_firestore")
    return errors
