"""Provider-free proof of the public SERVER -> GE -> OpenAI adapter seam."""

from __future__ import annotations

from types import SimpleNamespace

from generationengine import GenerationClient
from generationengine.providers.openai_text import OpenAITextProvider

from statblocks_v1.application.provider import ProviderOutcomeKind, ProviderOptionsV1
from statblocks_v1.application.schema_compiler import CompiledSchemaV1
from statblocks_v1.infrastructure.ge_provider import GenerationEngineDefinitionProvider


class _RecordingResponses:
    def __init__(self, texts: list[str]) -> None:
        self._texts = iter(texts)
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        text = next(self._texts)
        return SimpleNamespace(
            id=f"resp_{len(self.calls)}",
            _request_id=f"req_{len(self.calls)}",
            output_text=text,
            model="gpt-5.6-luna",
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=3,
                input_tokens_details=SimpleNamespace(cached_tokens=0),
            ),
            refusal=None,
        )


def test_public_statblock_generation_omits_temperature_on_initial_and_repair_calls() -> None:
    prompt = "Create a concise fantasy creature."
    system = "Return a statblock definition."
    schema = CompiledSchemaV1(
        name="statblock_definition_v1",
        schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
            "additionalProperties": False,
        },
        compiler_version="test",
        fingerprint="sha256:test",
    )
    responses = _RecordingResponses(['{"name":7}', '{"name":"Ogre"}'])
    sdk_client = SimpleNamespace(responses=responses)
    generation_client = GenerationClient(
        text_provider=OpenAITextProvider(client=sdk_client)
    )
    provider = GenerationEngineDefinitionProvider(client=generation_client)

    outcome = provider.generate_definition(
        prompt=prompt,
        system=system,
        schema=schema,
        options=ProviderOptionsV1(model="", inference_budget_seconds=90),
    )

    assert outcome.kind is ProviderOutcomeKind.success
    assert outcome.payload == {"name": "Ogre"}
    assert outcome.provider == "openai"
    assert outcome.resolved_model == "gpt-5.6-luna"
    assert len(responses.calls) == 2

    initial, repair = responses.calls
    for call in (initial, repair):
        assert call["model"] == "gpt-5.6-luna"
        assert "temperature" not in call
        assert call["text"]["format"]["type"] == "json_schema"
        assert call["text"]["format"]["schema"]

    assert initial["input"] == prompt
    assert initial["instructions"] == system
    assert "did not satisfy the required schema" in repair["input"]
