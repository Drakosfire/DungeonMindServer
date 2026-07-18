"""DungeonBuddy statblock contract v1 bounded context.

Import rules (enforced by package layout and focused tests):

- ``domain`` may depend on the standard library and Pydantic only.
- ``application`` may depend on ``domain``.
- ``infrastructure`` may depend on ``domain`` / ``application`` plus external SDKs.
- ``api`` may depend on ``domain`` / ``application`` and FastAPI.
- Legacy generator packages must not be imported into ``domain``.
"""

CONTRACT_NAME = "dungeonmind.dungeonbuddy-statblocks"
CONTRACT_VERSION = "1.0.0"

__all__ = ["CONTRACT_NAME", "CONTRACT_VERSION"]
