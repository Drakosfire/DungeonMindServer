"""FastAPI dependencies for the v1 router.

Authentication reuses the shared DungeonBuddy internal-key comparison while
mapping failures into the typed v1 error envelope.

Constant names mirror ``routers.internal_auth`` so header/env contracts stay
aligned, without importing the ``routers`` package (its ``__init__`` loads
unrelated OAuth routers and credentials).

Production repository/service construction is configured from ``app.py`` (or
tests) through factory setters so this api layer never imports infrastructure.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Header

from statblocks_v1.api.http_errors import GenerationTransportError, StatblockV1HTTPError
from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.repositories import (
    CandidateRepository,
    StatblockPersistenceRepository,
)
from statblocks_v1.application.revisions import RevisionServiceV1
from statblocks_v1.config import ConfigurationError, StatblocksV1Settings
from statblocks_v1.domain.errors import (
    InternalServiceMisconfiguredError,
    UnauthorizedInternalClientError,
)
from statblocks_v1.domain.receipts import ValidationMode, ValidationReceiptV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

# Keep identical to routers.internal_auth (shared wire contract).
INTERNAL_KEY_HEADER = "X-DungeonBuddy-Internal-Key"
INTERNAL_KEY_ENV = "DUNGEONBUDDY_INTERNAL_API_KEY"

Validator = Callable[[StatblockDefinitionV1, ValidationMode, datetime], ValidationReceiptV1]
Clock = Callable[[], datetime]

_candidate_repository_factory: Callable[[], CandidateRepository] | None = None
_persistence_repository_factory: Callable[[], StatblockPersistenceRepository] | None = None
_generation_service_factory: Callable[[], GenerationServiceV1] | None = None
_revision_service_factory: Callable[[], RevisionServiceV1] | None = None


def configure_candidate_repository_factory(
    factory: Callable[[], CandidateRepository] | None,
) -> None:
    global _candidate_repository_factory
    _candidate_repository_factory = factory


def configure_persistence_repository_factory(
    factory: Callable[[], StatblockPersistenceRepository] | None,
) -> None:
    global _persistence_repository_factory
    _persistence_repository_factory = factory


def configure_generation_service_factory(
    factory: Callable[[], GenerationServiceV1] | None,
) -> None:
    global _generation_service_factory
    _generation_service_factory = factory


def configure_revision_service_factory(
    factory: Callable[[], RevisionServiceV1] | None,
) -> None:
    global _revision_service_factory
    _revision_service_factory = factory


async def require_internal_service_auth(
    x_dungeonbuddy_internal_key: Annotated[
        str | None,
        Header(alias=INTERNAL_KEY_HEADER),
    ] = None,
) -> None:
    """Require the DungeonBuddy internal API key for all v1 routes."""
    expected_key = os.getenv(INTERNAL_KEY_ENV)
    if not expected_key:
        raise StatblockV1HTTPError(503, InternalServiceMisconfiguredError())

    if x_dungeonbuddy_internal_key is None:
        raise StatblockV1HTTPError(
            401,
            UnauthorizedInternalClientError("Missing internal API key"),
        )

    if not secrets.compare_digest(x_dungeonbuddy_internal_key, expected_key):
        raise StatblockV1HTTPError(
            403,
            UnauthorizedInternalClientError("Invalid internal API key"),
        )


async def require_generation_enabled() -> None:
    """Fail generation closed while preserving configured persisted-resource reads."""
    try:
        settings = StatblocksV1Settings.from_environment()
    except ConfigurationError:
        raise StatblockV1HTTPError(503, InternalServiceMisconfiguredError()) from None
    if not settings.feature_enabled:
        raise StatblockV1HTTPError(
            503,
            GenerationTransportError(
                "generation_disabled",
                "Statblock generation is disabled",
            ),
        )
    if not settings.openai_api_key:
        raise StatblockV1HTTPError(
            503,
            GenerationTransportError(
                "provider_not_configured",
                "Statblock generation is not configured",
            ),
        )


def get_candidate_repository() -> CandidateRepository:
    if _candidate_repository_factory is None:
        raise StatblockV1HTTPError(
            503,
            InternalServiceMisconfiguredError("Candidate repository is not configured"),
        )
    return _candidate_repository_factory()


def get_persistence_repository() -> StatblockPersistenceRepository:
    if _persistence_repository_factory is None:
        raise StatblockV1HTTPError(
            503,
            InternalServiceMisconfiguredError("Persistence repository is not configured"),
        )
    return _persistence_repository_factory()


def get_generation_service() -> GenerationServiceV1:
    if _generation_service_factory is None:
        raise StatblockV1HTTPError(
            503,
            InternalServiceMisconfiguredError("Generation service is not configured"),
        )
    return _generation_service_factory()


def get_revision_service() -> RevisionServiceV1:
    if _revision_service_factory is not None:
        return _revision_service_factory()
    # Default composition uses already-configured repository factories.
    return RevisionServiceV1(
        persistence=get_persistence_repository(),
        candidates=get_candidate_repository(),
        clock=get_clock(),
    )


def get_validator() -> Validator:
    return lambda definition, mode, validated_at: validate_definition(
        definition, mode, validated_at=validated_at
    )


def get_clock() -> Clock:
    return lambda: datetime.now(timezone.utc)
