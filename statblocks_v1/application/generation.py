"""Application service for generation and revision candidate workflows."""
from __future__ import annotations

import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import ValidationError

from statblocks_v1.application.commands import (
    AssetBriefV1,
    GenerateStatblockCommandV1,
    ReviseStatblockCommandV1,
)
from statblocks_v1.application.prompts import build_generation_prompt, build_revision_prompt
from statblocks_v1.application.provider import (
    DefinitionProvider,
    ProviderOptionsV1,
    ProviderOutcomeKind,
)
from statblocks_v1.application.schema_compiler import compile_openai_definition_schema
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.application.repositories import CandidateRepository
from statblocks_v1.domain.receipts import ValidationMode
from statblocks_v1.domain.resources import (
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
    ResourceLocatorV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

Clock = Callable[[], datetime]
CandidateIdFactory = Callable[[], str]


class DefinitionResolver(Protocol):
    def resolve(self, locator: ResourceLocatorV1) -> StatblockDefinitionV1: ...


class AssetGenerator(Protocol):
    def generate(self, brief: AssetBriefV1) -> list[dict[str, object]]: ...


@dataclass(frozen=True)
class GenerationFailureV1:
    kind: str
    message: str


GenerationResultV1 = GeneratedStatblockCandidateV1 | GenerationFailureV1


class GenerationServiceV1:
    """Coordinates provider output without letting provider metadata enter the definition."""

    def __init__(
        self,
        *,
        provider: DefinitionProvider,
        candidates: CandidateRepository,
        settings: GenerationSettingsV1,
        clock: Clock | None = None,
        candidate_id_factory: CandidateIdFactory | None = None,
        definition_resolver: DefinitionResolver | None = None,
        asset_generator: AssetGenerator | None = None,
    ) -> None:
        self._provider = provider
        self._candidates = candidates
        self._settings = settings
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._candidate_id_factory = candidate_id_factory or _new_candidate_id
        self._definition_resolver = definition_resolver
        self._asset_generator = asset_generator

    def generate(self, command: GenerateStatblockCommandV1) -> GenerationResultV1:
        return self._run(
            request_id=command.request_id,
            prompt=build_generation_prompt(command),
            source_digest=command.source.description_digest or _digest_text(command.source.description),
            source_locator=None,
            asset_prompt=command.source.description if command.asset_options.include_generation_brief else None,
            generate_assets=command.asset_options.generate_images,
        )

    def revise(self, command: ReviseStatblockCommandV1) -> GenerationResultV1:
        source = command.source_definition
        if source is None:
            if self._definition_resolver is None:
                return GenerationFailureV1("source_unavailable", "No definition resolver is configured")
            source = self._definition_resolver.resolve(command.source_locator)  # type: ignore[arg-type]
        return self._run(
            request_id=command.request_id,
            prompt=build_revision_prompt(command, source),
            source_digest=(command.source.description_digest if command.source else None),
            source_locator=command.source_locator,
            asset_prompt=(command.source.description if command.source and command.asset_options.include_generation_brief else None),
            generate_assets=command.asset_options.generate_images,
        )

    def _run(
        self,
        *,
        request_id: str,
        prompt: str,
        source_digest: str | None,
        source_locator: ResourceLocatorV1 | None,
        asset_prompt: str | None,
        generate_assets: bool,
    ) -> GenerationResultV1:
        compiled = compile_openai_definition_schema()
        started = time.monotonic()
        outcome = self._provider.generate_definition(
            prompt=prompt,
            schema=compiled,
            options=ProviderOptionsV1(
                model=self._settings.model,
                timeout_seconds=self._settings.timeout_seconds,
                max_retries=self._settings.max_retries,
            ),
        )
        if outcome.kind is not ProviderOutcomeKind.success:
            return GenerationFailureV1(f"provider_{outcome.kind.value}", outcome.message or "Provider did not return a definition")
        try:
            definition = StatblockDefinitionV1.model_validate(outcome.payload)
        except ValidationError:
            return GenerationFailureV1("definition_invalid", "Provider output does not match StatblockDefinitionV1")
        now = self._clock()
        receipt = validate_definition(
            definition, ValidationMode.generation_candidate, validated_at=now
        )
        if not receipt.is_persistence_ready:
            return GenerationFailureV1("definition_invalid", "Provider output has structural or reference errors")
        candidate = GeneratedStatblockCandidateV1(
            candidate_id=self._candidate_id_factory(),
            definition=definition,
            validation_receipt=receipt,
            generation_receipt=GenerationReceiptV1(
                request_id=request_id,
                provider=self._provider.provider_name,
                model=self._settings.model,
                prompt_version="statblock-generation-prompt-v1",
                schema_version=compiled.compiler_version,
                schema_fingerprint=compiled.fingerprint,
                generated_at=now,
                source_description_digest=source_digest,
                source_locator=source_locator,
                provider_request_id=outcome.request_id,
                provider_response_id=outcome.response_id,
                latency_ms=outcome.latency_ms or int((time.monotonic() - started) * 1000),
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
            ),
            asset_brief=AssetBriefV1(prompt=asset_prompt).model_dump(mode="json") if asset_prompt else None,
            assets=[],
            asset_warnings=[],
            created_at=now,
            expires_at=now + timedelta(seconds=self._settings.candidate_ttl_seconds),
            source_locator=source_locator,
        )
        if asset_prompt and generate_assets and self._asset_generator is not None:
            try:
                assets = self._asset_generator.generate(AssetBriefV1(prompt=asset_prompt))
                candidate = candidate.model_copy(update={"assets": assets})
            except Exception:
                candidate = candidate.model_copy(
                    update={"asset_warnings": ["Asset generation failed; review the candidate without assets."]}
                )
        return self._candidates.create(candidate)


def _digest_text(value: str) -> str:
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _new_candidate_id() -> str:
    return f"cand_{_base36(secrets.randbelow(36**16))}"


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = "0"
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result.lstrip("0")
    return result
