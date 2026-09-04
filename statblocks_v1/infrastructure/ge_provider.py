"""GenerationEngine-backed Statblocks v1 definition provider.

Runs in the worker thread created by asyncio.to_thread. It must not be
invoked from a running request-loop context.
"""
from __future__ import annotations

import asyncio

from generationengine import (
    FailureCode,
    GenerationClient,
    GenerationEngineError,
    InferenceProfile,
    TextRequest,
)
from statblocks_v1.application.provider import (
    ProviderOptionsV1,
    ProviderOutcomeKind,
    ProviderOutcomeV1,
)
from statblocks_v1.application.schema_compiler import CompiledSchemaV1

_KIND_BY_FAILURE = {
    FailureCode.PROVIDER_REFUSED: ProviderOutcomeKind.refusal,
    FailureCode.RATE_LIMITED: ProviderOutcomeKind.rate_limit,
    FailureCode.PROVIDER_TIMEOUT: ProviderOutcomeKind.timeout,
    FailureCode.STRUCTURED_OUTPUT_INVALID: ProviderOutcomeKind.incomplete,
    FailureCode.MALFORMED_PROVIDER_RESPONSE: ProviderOutcomeKind.incomplete,
    FailureCode.STREAM_INCOMPLETE: ProviderOutcomeKind.incomplete,
}


class GenerationEngineDefinitionProvider:
    provider_name = "generationengine"

    def __init__(
        self,
        client: GenerationClient | None = None,
        *,
        profile: InferenceProfile = InferenceProfile.STRUCTURED_HIGH_RELIABILITY,
    ) -> None:
        self._client = client
        self._profile = profile

    def generate_definition(
        self,
        *,
        prompt: str,
        system: str,
        schema: CompiledSchemaV1,
        options: ProviderOptionsV1,
    ) -> ProviderOutcomeV1:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "GenerationEngineDefinitionProvider must not run inside an active event loop"
            )

        client = self._client or GenerationClient.from_env()
        explicit_model = options.model.strip() if options.model and options.model.strip() else None
        request = TextRequest(
            user_prompt=prompt,
            system_prompt=system,
            profile=self._profile,
            model=explicit_model,
            json_schema=schema.schema,
            schema_name=schema.name,
            deadline_ms=int(options.inference_budget_seconds * 1000),
        )
        try:
            result = asyncio.run(client.generate_structured(request))
        except GenerationEngineError as error:
            return _outcome_from_observation(
                _KIND_BY_FAILURE.get(error.failure.code, ProviderOutcomeKind.failure),
                error.observation,
                message=error.failure.message,
            )
        if not result.parsed:
            return _outcome_from_observation(
                ProviderOutcomeKind.incomplete,
                result.observation,
                message="Provider returned no JSON",
            )
        return _outcome_from_observation(
            ProviderOutcomeKind.success,
            result.observation,
            payload=result.parsed,
        )


def _outcome_from_observation(
    kind: ProviderOutcomeKind,
    observation,
    *,
    message: str | None = None,
    payload: dict | None = None,
) -> ProviderOutcomeV1:
    return ProviderOutcomeV1(
        kind,
        payload=payload,
        message=message,
        request_id=observation.provider_request_id,
        response_id=observation.provider_response_id,
        latency_ms=observation.latency_ms,
        input_tokens=observation.input_tokens,
        output_tokens=observation.output_tokens,
        provider=observation.provider,
        resolved_model=observation.resolved_model,
        response_model=observation.response_model,
    )
