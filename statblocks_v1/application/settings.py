"""Environment settings for the structured-generation provider."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def _policy_model() -> str:
    policy_path = Path(__file__).resolve().parents[3] / "MODEL_POLICY.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    role = policy["actions"]["structured_generation"]
    return policy["models"][role]


@dataclass(frozen=True)
class GenerationSettingsV1:
    model: str
    timeout_seconds: float
    max_retries: int
    candidate_ttl_seconds: int

    @classmethod
    def from_environment(cls) -> "GenerationSettingsV1":
        return cls(
            model=os.getenv("STATBLOCKS_V1_OPENAI_MODEL", _policy_model()),
            timeout_seconds=float(os.getenv("STATBLOCKS_V1_OPENAI_TIMEOUT_SECONDS", "45")),
            max_retries=int(os.getenv("STATBLOCKS_V1_OPENAI_MAX_RETRIES", "1")),
            candidate_ttl_seconds=int(os.getenv("STATBLOCKS_V1_CANDIDATE_TTL_SECONDS", "86400")),
        )
