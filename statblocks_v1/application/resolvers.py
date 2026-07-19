"""Definition resolvers that speak PR15 persistence read contracts."""
from __future__ import annotations

from statblocks_v1.application.repositories import StatblockPersistenceRepository
from statblocks_v1.domain.resources import ExactRevisionLocatorV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1


class PersistenceDefinitionResolver:
    """Resolve an exact revision through ``get_revision(statblock_id, revision_id)``."""

    def __init__(self, repository: StatblockPersistenceRepository) -> None:
        self._repository = repository

    def resolve(self, locator: ExactRevisionLocatorV1) -> StatblockDefinitionV1:
        return self._repository.get_revision(
            locator.statblock_id, locator.revision_id
        ).definition
