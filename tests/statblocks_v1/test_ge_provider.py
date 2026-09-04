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


def _options() -> ProviderOptionsV1:
    return ProviderOptionsV1(model="gpt-5.6-luna", timeout_seconds=45, max_retries=1)


def _observation(**overrides):
    payload = dict(
        provider="openai",
        requested_profile="structured_high_reliability",
        requested_model="gpt-5.6-luna",
        resolved_model="gpt-5.6-luna",
        provider_request_id="req-1",
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


def test_generate_definition_maps_success_and_tokens() -> None:
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
    assert client.calls[0].model == "gpt-5.6-luna"
    assert client.calls[0].deadline_ms == 45000


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
    assert outcome.message == "timed out"


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
