"""OpenAI Structured Outputs adapter; the domain never imports this module."""
from __future__ import annotations

import json
import time
from typing import Any

from statblocks_v1.application.provider import (
    ProviderOptionsV1,
    ProviderOutcomeKind,
    ProviderOutcomeV1,
)
from statblocks_v1.application.schema_compiler import CompiledSchemaV1


class OpenAIDefinitionProvider:
    provider_name = "openai"

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from openai import OpenAI

            client = OpenAI()
        self._client = client

    def generate_definition(
        self, *, prompt: str, schema: CompiledSchemaV1, options: ProviderOptionsV1
    ) -> ProviderOutcomeV1:
        started = time.monotonic()
        try:
            client = (
                self._client.with_options(timeout=options.timeout_seconds, max_retries=options.max_retries)
                if hasattr(self._client, "with_options")
                else self._client
            )
            response = client.chat.completions.create(
                model=options.model,
                messages=[
                    {"role": "system", "content": "Return only the requested JSON schema instance."},
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": schema.name, "strict": True, "schema": schema.schema},
                },
            )
            message = response.choices[0].message
            metadata = _metadata(response, started)
            if getattr(message, "refusal", None):
                return ProviderOutcomeV1(ProviderOutcomeKind.refusal, message="Provider refused request", **metadata)
            content = getattr(message, "content", None)
            if not content:
                return ProviderOutcomeV1(ProviderOutcomeKind.incomplete, message="Provider returned no JSON", **metadata)
            try:
                return ProviderOutcomeV1.succeeded(json.loads(content), **metadata)
            except json.JSONDecodeError:
                return ProviderOutcomeV1(ProviderOutcomeKind.incomplete, message="Provider returned malformed JSON", **metadata)
        except Exception as exc:
            name = type(exc).__name__.lower()
            kind = (
                ProviderOutcomeKind.rate_limit if "ratelimit" in name else
                ProviderOutcomeKind.timeout if "timeout" in name else
                ProviderOutcomeKind.failure
            )
            return ProviderOutcomeV1(kind, message="OpenAI request failed", latency_ms=int((time.monotonic() - started) * 1000))


def _metadata(response: Any, started: float) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    return {
        "request_id": getattr(response, "_request_id", None),
        "response_id": getattr(response, "id", None),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "input_tokens": getattr(usage, "prompt_tokens", None),
        "output_tokens": getattr(usage, "completion_tokens", None),
    }
