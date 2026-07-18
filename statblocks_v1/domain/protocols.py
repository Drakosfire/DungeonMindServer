"""Narrow dependency seams for later PRs.

These protocols intentionally declare only the capability shape. Concrete
infrastructure adapters and repository methods land in later stacked PRs.

Empty placeholder protocols are not ``@runtime_checkable``: an empty structural
protocol is satisfied by any object, which makes ``isinstance`` checks misleading.
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


class GenerationProvider(Protocol):
    """Structured Outputs provider seam (implemented in PR16)."""


class CandidateRepository(Protocol):
    """Candidate persistence seam (implemented in PR15)."""


class StatblockRepository(Protocol):
    """Logical statblock persistence seam (implemented in PR15)."""


class RevisionRepository(Protocol):
    """Immutable revision persistence seam (implemented in PR15)."""


class AssetGateway(Protocol):
    """Asset reference gateway seam (implemented in PR19)."""
