"""Environment settings for the structured-generation provider."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from statblocks_v1.domain.errors import InternalServiceMisconfiguredError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _policy_model() -> str:
    """Resolve structured_generation from the in-repo MODEL_POLICY.json only."""
    policy_path = _REPO_ROOT / "MODEL_POLICY.json"
    if not policy_path.is_file():
        raise InternalServiceMisconfiguredError(
            "MODEL_POLICY.json is missing from the DungeonMindServer repository root"
        )
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        role = policy["actions"]["structured_generation"]
        return policy["models"][role]
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise InternalServiceMisconfiguredError(
            "MODEL_POLICY.json does not define actions.structured_generation"
        ) from error


@dataclass(frozen=True)
class GenerationSettingsV1:
    model: str
    timeout_seconds: float
    max_retries: int
    candidate_ttl_seconds: int

    @classmethod
    def from_environment(cls) -> "GenerationSettingsV1":
        configured = os.getenv("STATBLOCKS_V1_OPENAI_MODEL")
        return cls(
            model=configured if configured else _policy_model(),
            timeout_seconds=float(os.getenv("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", "45")),
            max_retries=int(os.getenv("STATBLOCKS_V1_OPENAI_MAX_RETRIES", "1")),
            candidate_ttl_seconds=int(os.getenv("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", "86400")),
        )
