"""Shared GenerationEngine client construction."""

from __future__ import annotations

from generationengine import GenerationClient

_client: GenerationClient | None = None


def get_generation_client() -> GenerationClient:
    global _client
    if _client is None:
        _client = GenerationClient.from_env()
    return _client
