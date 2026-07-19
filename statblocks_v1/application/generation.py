"""Application service for generation and revision candidate workflows."""
from __future__ import annotations

import hashlib
import secrets
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from pydantic import ValidationError

from statblocks_v1.application.commands import (
    AssetBriefV1,
    CallerProvenanceV1,
    GenerateStatblockCommandV1,
    ReviseStatblockCommandV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.prompts import PROMPT_VERSION, build_generation_prompt, build_revision_prompt
from statblocks_v1.application.provider import (
    DefinitionProvider,
    ProviderOptionsV1,
    ProviderOutcomeKind,
)
from statblocks_v1.application.repositories import CandidateRepository
from statblocks_v1.application.schema_compiler import compile_openai_definition_schema
from statblocks_v1.application.settings import GenerationSettingsV1
from statblocks_v1.domain.errors import StatblockV1Error
from statblocks_v1.domain.profiles import RulesetRef
from statblocks_v1.domain.receipts import (
    ValidationIssueV1,
    ValidationMode,
    ValidationReceiptV1,
    ValidationSeverity,
    ValidationStatus,
)
from statblocks_v1.domain.resources import (
    ExactRevisionLocatorV1,
    GeneratedStatblockCandidateV1,
    GenerationReceiptV1,
)
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
from statblocks_v1.domain.validation import validate_definition

Clock = Callable[[], datetime]
CandidateIdFactory = Callable[[], str]


class DefinitionResolver(Protocol):
    def resolve(self, locator: ExactRevisionLocatorV1) -> StatblockDefinitionV1: ...


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
        digest_error = _verified_source_digest(command.source)
        if isinstance(digest_error, GenerationFailureV1):
            return digest_error
        source_digest = digest_error
        return self._run(
            request_id=command.request_id,
            ruleset=command.ruleset,
            caller=command.caller,
            prompt=build_generation_prompt(command),
            source_digest=source_digest,
            source_locator=None,
            source_definition=None,
            preserve_element_keys=False,
            asset_prompt=(
                command.source.description if command.asset_options.include_generation_brief else None
            ),
            generate_assets=command.asset_options.generate_images,
        )

    def revise(self, command: ReviseStatblockCommandV1) -> GenerationResultV1:
        source = command.source_definition
        source_locator = command.source_locator
        if source is None:
            if source_locator is None:
                return GenerationFailureV1("invalid_request", "Revision source is missing")
            if self._definition_resolver is None:
                return GenerationFailureV1(
                    "source_unavailable", "No definition resolver is configured"
                )
            try:
                source = self._definition_resolver.resolve(source_locator)
            except StatblockV1Error as error:
                return GenerationFailureV1(error.code, error.message)
            except Exception:
                return GenerationFailureV1(
                    "source_unavailable", "Failed to resolve source revision"
                )

        source_digest: str | None = None
        if command.source is not None:
            digest_error = _verified_source_digest(command.source)
            if isinstance(digest_error, GenerationFailureV1):
                return digest_error
            source_digest = digest_error

        return self._run(
            request_id=command.request_id,
            ruleset=command.ruleset,
            caller=command.caller,
            prompt=build_revision_prompt(command, source),
            source_digest=source_digest,
            source_locator=source_locator,
            source_definition=source,
            preserve_element_keys=command.preserve_element_keys,
            asset_prompt=(
                command.source.description
                if command.source and command.asset_options.include_generation_brief
                else None
            ),
            generate_assets=command.asset_options.generate_images,
        )

    def _run(
        self,
        *,
        request_id: str,
        ruleset: RulesetRef,
        caller: CallerProvenanceV1,
        prompt: str,
        source_digest: str | None,
        source_locator: ExactRevisionLocatorV1 | None,
        source_definition: StatblockDefinitionV1 | None,
        preserve_element_keys: bool,
        asset_prompt: str | None,
        generate_assets: bool,
    ) -> GenerationResultV1:
        compiled = compile_openai_definition_schema()
        started = time.monotonic()
        try:
            outcome = self._provider.generate_definition(
                prompt=prompt,
                schema=compiled,
                options=ProviderOptionsV1(
                    model=self._settings.model,
                    timeout_seconds=self._settings.timeout_seconds,
                    max_retries=self._settings.max_retries,
                ),
            )
        except Exception:
            return GenerationFailureV1(
                "provider_failure", "Provider raised an unexpected error"
            )
        if outcome.kind is not ProviderOutcomeKind.success:
            return GenerationFailureV1(
                f"provider_{outcome.kind.value}",
                outcome.message or "Provider did not return a definition",
            )
        if outcome.payload is None:
            return GenerationFailureV1(
                "provider_incomplete", "Provider returned no definition payload"
            )
        try:
            definition = StatblockDefinitionV1.model_validate(outcome.payload)
        except ValidationError:
            return GenerationFailureV1(
                "definition_invalid", "Provider output does not match StatblockDefinitionV1"
            )
        if not _ruleset_matches(definition.ruleset, ruleset):
            return GenerationFailureV1(
                "ruleset_mismatch",
                "Generated definition ruleset does not match the requested ruleset",
            )

        now = self._clock()
        receipt = validate_definition(
            definition, ValidationMode.generation_candidate, validated_at=now
        )
        if receipt.status is ValidationStatus.invalid:
            return GenerationFailureV1(
                "definition_invalid", "Provider output has structural or reference errors"
            )
        if source_definition is not None and preserve_element_keys:
            receipt = _with_key_preservation_warnings(receipt, source_definition, definition)

        asset_warnings: list[str] = []
        assets: list[dict[str, object]] = []
        if generate_assets:
            if self._asset_generator is None:
                asset_warnings.append(
                    "Asset generation was requested but no asset generator is configured."
                )
            else:
                try:
                    assets = self._asset_generator.generate(AssetBriefV1(prompt=asset_prompt or definition.identity.name))
                except Exception:
                    asset_warnings.append(
                        "Asset generation failed; review the candidate without assets."
                    )

        candidate = GeneratedStatblockCandidateV1(
            candidate_id=self._candidate_id_factory(),
            definition=definition,
            validation_receipt=receipt,
            generation_receipt=GenerationReceiptV1(
                request_id=request_id,
                provider=self._provider.provider_name,
                model=self._settings.model,
                prompt_version=PROMPT_VERSION,
                schema_version=compiled.compiler_version,
                schema_fingerprint=compiled.fingerprint,
                generated_at=now,
                caller_scope=caller.caller_scope,
                actor=caller.actor,
                source_description_digest=source_digest,
                source_locator=source_locator,
                provider_request_id=outcome.request_id,
                provider_response_id=outcome.response_id,
                latency_ms=outcome.latency_ms or int((time.monotonic() - started) * 1000),
                input_tokens=outcome.input_tokens,
                output_tokens=outcome.output_tokens,
            ),
            asset_brief=AssetBriefV1(prompt=asset_prompt).model_dump(mode="json") if asset_prompt else None,
            assets=assets,
            asset_warnings=asset_warnings,
            created_at=now,
            expires_at=now + timedelta(seconds=self._settings.candidate_ttl_seconds),
            source_locator=source_locator,
        )
        return self._candidates.create(candidate)


def _verified_source_digest(source: SourceSnapshotV1) -> str | GenerationFailureV1:
    computed = _digest_text(source.description)
    if source.description_digest is not None and source.description_digest != computed:
        return GenerationFailureV1(
            "source_digest_mismatch",
            "Caller-supplied source description digest does not match the description",
        )
    return computed


def _ruleset_matches(actual: RulesetRef, requested: RulesetRef) -> bool:
    return (
        actual.system == requested.system
        and actual.edition == requested.edition
        and actual.house_ruleset_id == requested.house_ruleset_id
    )


def _with_key_preservation_warnings(
    receipt: ValidationReceiptV1,
    source: StatblockDefinitionV1,
    revised: StatblockDefinitionV1,
) -> ValidationReceiptV1:
    issues = list(receipt.issues)
    revised_by_identity = {
        (_element_identity(element.section.value, element.name)): element
        for element in revised.rule_elements
    }
    revised_keys = {element.key for element in revised.rule_elements}
    for index, element in enumerate(source.rule_elements):
        identity = _element_identity(element.section.value, element.name)
        match = revised_by_identity.get(identity)
        if match is None:
            if element.key not in revised_keys:
                issues.append(
                    ValidationIssueV1(
                        code="ELEMENT_KEY_DROPPED",
                        severity=ValidationSeverity.warning,
                        field_path=f"rule_elements[{index}].key",
                        message=(
                            f"Source element key '{element.key}' was not preserved; "
                            "confirm the conceptual rule was intentionally replaced."
                        ),
                    )
                )
            continue
        if match.key != element.key:
            revised_index = next(
                i for i, item in enumerate(revised.rule_elements) if item.key == match.key
            )
            issues.append(
                ValidationIssueV1(
                    code="ELEMENT_KEY_CHANGED",
                    severity=ValidationSeverity.warning,
                    field_path=f"rule_elements[{revised_index}].key",
                    message=(
                        f"Element '{element.name}' changed key from '{element.key}' "
                        f"to '{match.key}' despite preserve_element_keys."
                    ),
                )
            )
    status = (
        ValidationStatus.invalid
        if any(issue.severity is ValidationSeverity.error for issue in issues)
        else ValidationStatus.warnings
        if issues
        else ValidationStatus.valid
    )
    return receipt.model_copy(update={"issues": issues, "status": status})


def _element_identity(section: str, name: str) -> tuple[str, str]:
    return (section, unicodedata.normalize("NFC", name).casefold())


def _digest_text(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _new_candidate_id() -> str:
    return f"cand_{_base36(secrets.randbelow(36**16))}"


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    result = "0"
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result.lstrip("0")
    return result
