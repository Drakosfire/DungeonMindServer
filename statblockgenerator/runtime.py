"""Shared StatBlockGenerator runtime for legacy app and v2 compatibility routers.

Both routers must use this factory so production startup constructs a single
generator (and therefore a single OpenAI client when the key is present).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from statblockgenerator.statblock_generator import StatBlockGenerator

_generator: StatBlockGenerator | None = None


def configure_statblock_generator(generator: StatBlockGenerator | None) -> None:
    """Override or clear the shared instance (tests / explicit app composition)."""
    global _generator
    _generator = generator


def get_statblock_generator() -> StatBlockGenerator:
    """Return the process-wide StatBlockGenerator, constructing it once."""
    global _generator
    if _generator is None:
        from statblockgenerator.statblock_generator import StatBlockGenerator

        _generator = StatBlockGenerator()
    return _generator
