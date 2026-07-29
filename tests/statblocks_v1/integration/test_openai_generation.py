"""Opt-in smoke coverage for the real Structured Outputs adapter."""
from __future__ import annotations

import os

import pytest

from statblocks_v1.application.prompts import build_system_prompt
from statblocks_v1.application.provider import ProviderOptionsV1, ProviderOutcomeKind
from statblocks_v1.application.schema_compiler import compile_openai_definition_schema
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.infrastructure.openai_provider import OpenAIDefinitionProvider

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_OPENAI_GENERATION_TESTS") or not os.getenv("OPENAI_API_KEY"),
    reason="requires RUN_OPENAI_GENERATION_TESTS=1 and OPENAI_API_KEY",
)


def _options() -> ProviderOptionsV1:
    settings = GenerationSettingsV1.from_environment()
    return ProviderOptionsV1(
        model=settings.model,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def test_openai_simple_generation_validates_against_canonical_model() -> None:
    provider = OpenAIDefinitionProvider()
    schema = compile_openai_definition_schema()
    prompt = """
You produce only a StatblockDefinitionV1 JSON object for D&D 5e 2024.
Create one Medium humanoid named 'Gate Scout' with CR 1, walking speed 30 feet,
Strength 12 Dexterity 14 Constitution 12 Intelligence 10 Wisdom 12 Charisma 10,
one simple melee attack, and no outer envelope or server metadata.
definition.ruleset must be {"system":"dnd5e","edition":"2024","house_ruleset_id":null}.
"""
    outcome = provider.generate_definition(
        prompt=prompt,
        system=build_system_prompt("2024"),
        schema=schema,
        options=_options(),
    )

    assert outcome.kind is ProviderOutcomeKind.success
    assert outcome.payload is not None
    definition = StatblockDefinitionV1.model_validate(outcome.payload)
    dumped = definition.model_dump(mode="json")
    assert "candidate_id" not in dumped
    assert "created_at" not in dumped
    assert definition.ruleset.edition.value == "2024"


def test_openai_advanced_generation_validates_against_canonical_model() -> None:
    provider = OpenAIDefinitionProvider()
    schema = compile_openai_definition_schema()
    prompt = """
You produce only a StatblockDefinitionV1 JSON object for D&D 5e 2024.
Create one Large dragon named 'Ashen Coil' with CR 10, legendary actions using a
legendary_actions resource pool, flight, and at least one recharge breath weapon.
Do not emit candidate IDs, digests, timestamps, or provenance.
definition.ruleset must be {"system":"dnd5e","edition":"2024","house_ruleset_id":null}.
"""
    outcome = provider.generate_definition(
        prompt=prompt,
        system=build_system_prompt("2024"),
        schema=schema,
        options=_options(),
    )

    assert outcome.kind is ProviderOutcomeKind.success
    assert outcome.payload is not None
    definition = StatblockDefinitionV1.model_validate(outcome.payload)
    assert definition.identity.name
    assert any(pool.key == "legendary_actions" for pool in definition.resources) or any(
        element.section.value == "legendary_action" for element in definition.rule_elements
    )
