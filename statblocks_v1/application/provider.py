"""Provider seam and stable outcomes for definition-only generation."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from statblocks_v1.application.schema_compiler import CompiledSchemaV1


class ProviderOutcomeKind(str, Enum):
    success = "success"
    refusal = "refusal"
    incomplete = "incomplete"
    timeout = "timeout"
    rate_limit = "rate_limit"
    failure = "failure"


@dataclass(frozen=True)
class ProviderOutcomeV1:
    kind: ProviderOutcomeKind
    payload: dict[str, Any] | None = None
    message: str | None = None
    request_id: str | None = None
    response_id: str | None = None
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @classmethod
    def succeeded(cls, payload: dict[str, Any], **metadata: Any) -> "ProviderOutcomeV1":
        return cls(kind=ProviderOutcomeKind.success, payload=payload, **metadata)


@dataclass(frozen=True)
class ProviderOptionsV1:
    model: str
    timeout_seconds: float
    max_retries: int


class DefinitionProvider(Protocol):
    provider_name: str

    def generate_definition(
        self, *, prompt: str, schema: CompiledSchemaV1, options: ProviderOptionsV1
    ) -> ProviderOutcomeV1: ...
