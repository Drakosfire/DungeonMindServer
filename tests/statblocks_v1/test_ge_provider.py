"""GenerationEngine Statblocks v1 adapter stays on the worker-thread side of asyncio.to_thread."""

from __future__ import annotations

import asyncio

import pytest
from generationengine import FailureCode, GenerationEngineError, InferenceFailure, TextResult
from generationengine.observation import InferenceObservation, ObservationState

from statblocks_v1.application.provider import ProviderOptionsV1, ProviderOutcomeKind
from statblocks_v1.application.schema_compiler import CompiledSchemaV1
from statblocks_v1.infrastructure.ge_provider import GenerationEngineDefinitionProvider


def _schema() -> CompiledSchemaV1:
    return CompiledSchemaV1(
        name="statblock_definition_v1",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        compiler_version="test",
        fingerprint="sha256:test",
    )


def _options(*, model: str = "") -> ProviderOptionsV1:
    return ProviderOptionsV1(model=model, inference_budget_seconds=90)


def _observation(**overrides):
    payload = dict(
        provider="openai",
        requested_profile="structured_high_reliability",
        requested_model=None,
        resolved_model="gpt-5.6-luna",
        provider_request_id="req-1",
        provider_response_id=None,
        input_tokens=10,
        output_tokens=20,
        latency_ms=7,
        retry_count=0,
        state=ObservationState.COMPLETED,
    )
    payload.update(overrides)
    return InferenceObservation(**payload)


class _FakeClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def generate_structured(self, request):
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return self.result


def test_generate_definition_defaults_to_profile_resolution() -> None:
    client = _FakeClient(
        result=TextResult(
            text=None,
            parsed={"name": "Ogre"},
            observation=_observation(),
        )
    )
    provider = GenerationEngineDefinitionProvider(client=client)
    outcome = provider.generate_definition(
        prompt="Make a brute",
        system="You write statblocks.",
        schema=_schema(),
        options=_options(),
    )
    assert outcome.kind is ProviderOutcomeKind.success
    assert outcome.payload == {"name": "Ogre"}
    assert outcome.input_tokens == 10
    assert outcome.output_tokens == 20
    assert outcome.provider == "openai"
    assert outcome.resolved_model == "gpt-5.6-luna"
    assert outcome.request_id == "req-1"
    assert outcome.response_id is None
    assert client.calls[0].model is None
    assert client.calls[0].profile.value == "structured_high_reliability"
    assert client.calls[0].deadline_ms == 90000


def test_generate_definition_passes_explicit_model_override() -> None:
    client = _FakeClient(
        result=TextResult(text=None, parsed={"name": "Ogre"}, observation=_observation())
    )
    GenerationEngineDefinitionProvider(client=client).generate_definition(
        prompt="x",
        system="s",
        schema=_schema(),
        options=_options(model="gpt-4o"),
    )
    assert client.calls[0].model == "gpt-4o"


def test_generate_definition_maps_timeout() -> None:
    failure = InferenceFailure.from_code(FailureCode.PROVIDER_TIMEOUT, "timed out")
    client = _FakeClient(
        error=GenerationEngineError(
            failure,
            _observation(
                state=ObservationState.FAILED,
                failure_code=FailureCode.PROVIDER_TIMEOUT,
            ),
        )
    )
    outcome = GenerationEngineDefinitionProvider(client=client).generate_definition(
        prompt="x",
        system="s",
        schema=_schema(),
        options=_options(),
    )
    assert outcome.kind is ProviderOutcomeKind.timeout
    assert outcome.message == "Provider request timed out."
    assert outcome.response_id is None


def test_generate_definition_rejects_running_event_loop() -> None:
    provider = GenerationEngineDefinitionProvider(client=_FakeClient())

    async def _inside_loop():
        provider.generate_definition(
            prompt="x",
            system="s",
            schema=_schema(),
            options=_options(),
        )

    with pytest.raises(RuntimeError, match="active event loop"):
        asyncio.run(_inside_loop())
