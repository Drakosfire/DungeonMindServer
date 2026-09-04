"""Environment settings for the structured-generation provider."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

from statblocks_v1.domain.errors import InternalServiceMisconfiguredError


@dataclass(frozen=True)
class GenerationSettingsV1:
    model: str
    timeout_seconds: float
    max_retries: int
    candidate_ttl_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.model, str):
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_OPENAI_MODEL must be a string"
            )
        if isinstance(self.timeout_seconds, bool) or not isinstance(
            self.timeout_seconds, (int, float)
        ):
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS must be a finite positive number"
            )
        if not math.isfinite(float(self.timeout_seconds)) or float(self.timeout_seconds) <= 0:
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS must be a finite positive number"
            )
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int):
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_OPENAI_MAX_RETRIES must be an integer >= 0"
            )
        if self.max_retries < 0:
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_OPENAI_MAX_RETRIES must be an integer >= 0"
            )
        if isinstance(self.candidate_ttl_seconds, bool) or not isinstance(
            self.candidate_ttl_seconds, int
        ):
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_CANDIDATE_TTL_SECONDS must be an integer > 0"
            )
        if self.candidate_ttl_seconds <= 0:
            raise InternalServiceMisconfiguredError(
                "STATBLOCKS_V1_CANDIDATE_TTL_SECONDS must be an integer > 0"
            )

    @classmethod
    def from_environment(cls) -> "GenerationSettingsV1":
        try:
            configured = os.getenv("STATBLOCKS_V1_OPENAI_MODEL")
            return cls(
                model=configured.strip() if configured and configured.strip() else "",
                timeout_seconds=float(
                    os.getenv("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", "45")
                ),
                max_retries=int(os.getenv("STATBLOCKS_V1_OPENAI_MAX_RETRIES", "1")),
                candidate_ttl_seconds=int(
                    os.getenv("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", "86400")
                ),
            )
        except InternalServiceMisconfiguredError:
            raise
        except (TypeError, ValueError) as error:
            raise InternalServiceMisconfiguredError(
                "Generation settings environment values are malformed"
            ) from error
