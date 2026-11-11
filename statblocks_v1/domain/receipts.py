"""Stable, transport-neutral validation receipts for statblock v1."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from statblocks_v1.domain.primitives import StrictModel

VALIDATOR_VERSION = "statblock-validator-v1.2"


class ValidationMode(str, Enum):
    generation_candidate = "generation_candidate"
    editor_preview = "editor_preview"
    persistence = "persistence"


class ValidationSeverity(str, Enum):
    info = "info"
    warning = "warning"
    error = "error"


class ValidationStatus(str, Enum):
    valid = "valid"
    warnings = "warnings"
    invalid = "invalid"


class ValidationIssueV1(StrictModel):
    """A stable, UI-addressable validation finding."""

    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    severity: ValidationSeverity
    field_path: str = Field(min_length=1)
    message: str = Field(min_length=1)
    suggested_resolution: str | None = None


class ValidationReceiptV1(StrictModel):
    """Deterministic outcome except for optional caller-supplied validation time."""

    status: ValidationStatus
    mode: ValidationMode
    validator_version: str
    canonicalizer_version: str
    issues: list[ValidationIssueV1] = Field(default_factory=list)
    definition_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    validated_at: datetime | None = None

    @property
    def is_persistence_ready(self) -> bool:
        """Whether this receipt proves persistence readiness.

        Only a receipt produced under :attr:`ValidationMode.persistence` may
        claim readiness. Candidate/preview modes downgrade some contradictions
        to warnings, so a warning-only candidate receipt must not be treated as
        persistence-ready.
        """

        if self.mode is not ValidationMode.persistence:
            return False
        return not any(issue.severity is ValidationSeverity.error for issue in self.issues)
