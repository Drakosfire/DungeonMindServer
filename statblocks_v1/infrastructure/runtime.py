"""Production dependency construction for the statblock v1 outer boundary.

Callers outside the package (``app.py``) supply the Firestore client so this
layer never imports repository-owned ``firestore`` packages directly.
"""

from __future__ import annotations

from typing import Any

from statblocks_v1.application.generation import GenerationServiceV1
from statblocks_v1.application.repositories import (
    CandidateRepository,
    StatblockPersistenceRepository,
)
from statblocks_v1.application.resolvers import PersistenceDefinitionResolver
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.infrastructure.firestore_repositories import (
    FirestoreCandidateRepository,
    FirestoreStatblockPersistenceRepository,
)
from statblocks_v1.infrastructure.openai_provider import OpenAIDefinitionProvider


def build_candidate_repository(client: Any) -> CandidateRepository:
    return FirestoreCandidateRepository(client)


def build_persistence_repository(client: Any) -> StatblockPersistenceRepository:
    return FirestoreStatblockPersistenceRepository(client)


def build_generation_service(
    *,
    client: Any | None = None,
    candidates: CandidateRepository | None = None,
    persistence: StatblockPersistenceRepository | None = None,
) -> GenerationServiceV1:
    candidate_repo = candidates or build_candidate_repository(client)
    persistence_repo = persistence or build_persistence_repository(client)
    return GenerationServiceV1(
        provider=OpenAIDefinitionProvider(),
        candidates=candidate_repo,
        settings=GenerationSettingsV1.from_environment(),
        definition_resolver=PersistenceDefinitionResolver(persistence_repo),
    )
