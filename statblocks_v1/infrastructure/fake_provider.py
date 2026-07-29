"""Deterministic definition provider used by offline tests and DI overrides."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from statblocks_v1.application.provider import ProviderOptionsV1, ProviderOutcomeV1
from statblocks_v1.application.schema_compiler import CompiledSchemaV1


class FakeDefinitionProvider:
    provider_name = "fake"

    def __init__(
        self,
        outcome: ProviderOutcomeV1 | dict[str, Any],
        *,
        callback: Callable[
            [str, str, CompiledSchemaV1, ProviderOptionsV1], ProviderOutcomeV1
        ]
        | None = None,
    ) -> None:
        self._outcome = outcome
        self._callback = callback
        self.calls: list[tuple[str, str, CompiledSchemaV1, ProviderOptionsV1]] = []

    def generate_definition(
        self,
        *,
        prompt: str,
        system: str,
        schema: CompiledSchemaV1,
        options: ProviderOptionsV1,
    ) -> ProviderOutcomeV1:
        self.calls.append((prompt, system, schema, options))
        if self._callback:
            return self._callback(prompt, system, schema, options)
        if isinstance(self._outcome, dict):
            return ProviderOutcomeV1.succeeded(self._outcome)
        return self._outcome
