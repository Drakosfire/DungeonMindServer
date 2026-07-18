"""Opt-in smoke coverage for the real Structured Outputs adapter."""
from __future__ import annotations

import os

import pytest

from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.infrastructure.openai_provider import OpenAIDefinitionProvider

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_OPENAI_GENERATION_TESTS") or not os.getenv("OPENAI_API_KEY"),
    reason="requires RUN_OPENAI_GENERATION_TESTS=1 and OPENAI_API_KEY",
)


def test_openai_provider_is_constructible_with_opt_in_credentials() -> None:
    """Network calls belong in a separately enabled smoke suite."""
    provider = OpenAIDefinitionProvider()

    assert provider.provider_name == "openai"
    assert GenerationSettingsV1.from_environment().model
