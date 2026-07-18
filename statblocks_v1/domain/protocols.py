"""Narrow dependency seams for later PRs.

These protocols intentionally declare only the capability shape. Concrete
infrastructure adapters and repository methods land in later stacked PRs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current UTC timestamp used for server envelopes."""


@runtime_checkable
class IdAllocator(Protocol):
    def allocate(self, prefix: str) -> str:
        """Allocate a server-owned opaque identifier with the given prefix."""


@runtime_checkable
class GenerationProvider(Protocol):
    """Structured Outputs provider seam (implemented in PR16)."""


@runtime_checkable
class CandidateRepository(Protocol):
    """Candidate persistence seam (implemented in PR15)."""


@runtime_checkable
class StatblockRepository(Protocol):
    """Logical statblock persistence seam (implemented in PR15)."""


@runtime_checkable
class RevisionRepository(Protocol):
    """Immutable revision persistence seam (implemented in PR15)."""


@runtime_checkable
class AssetGateway(Protocol):
    """Asset reference gateway seam (implemented in PR19)."""
