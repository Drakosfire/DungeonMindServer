"""Falsification harness for statblock prompt/schema guidance ablations.

Measures error-severity domain-validator codes across harness-owned ablation arms.
Requires opt-in env (RUN_OPENAI_GENERATION_TESTS=1 and OPENAI_API_KEY); never for CI.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "Docs/Design/fixtures/prompt-eval"

MINIMAL_SYSTEM = "Return only the requested JSON schema instance."

ALL_ARMS = ("bare", "schema-only", "prompt-only", "both")

# Import after ROOT is known; package is installed via uv workspace.
from statblocks_v1.application.commands import (  # noqa: E402
    AssetOptionsV1,
    CallerProvenanceV1,
    EncounterContextV1,
    GenerateStatblockCommandV1,
    GenerationIntentV1,
    SourceSnapshotV1,
)
from statblocks_v1.application.prompts import build_generation_prompt, build_system_prompt  # noqa: E402
from statblocks_v1.application.provider import ProviderOptionsV1, ProviderOutcomeKind  # noqa: E402
from statblocks_v1.application.schema_compiler import (  # noqa: E402
    SCHEMA_COMPILER_VERSION,
    CompiledSchemaV1,
    compile_openai_definition_schema,
)
from statblocks_v1.application.settings import GenerationSettingsV1  # noqa: E402
from statblocks_v1.domain.profiles import RulesetEdition, RulesetRef, RulesetSystem  # noqa: E402
from statblocks_v1.domain.receipts import ValidationMode, ValidationSeverity  # noqa: E402
from statblocks_v1.domain.rule_elements import StatblockDefinitionV1  # noqa: E402
from statblocks_v1.domain.validation import validate_definition  # noqa: E402
from statblocks_v1.infrastructure.openai_provider import OpenAIDefinitionProvider  # noqa: E402


@dataclass(frozen=True)
class Fixture:
    name: str
    name_hint: str
    description: str


@dataclass
class TrialResult:
    fixture: str
    arm: str
    trial: int
    outcome_kind: str
    error_codes: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    message: str | None = None


@dataclass
class ArmSummary:
    arm: str
    trials: int = 0
    clean_trials: int = 0
    provider_failures: Counter[str] = field(default_factory=Counter)
    error_code_counts: Counter[str] = field(default_factory=Counter)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    api_calls: int = 0


def _load_environment() -> None:
    env_path = ROOT / ".env.development"
    if env_path.is_file():
        load_dotenv(env_path, override=False)


def _require_live_env() -> None:
    if not os.getenv("RUN_OPENAI_GENERATION_TESTS"):
        raise SystemExit(
            "Refusing to call OpenAI: set RUN_OPENAI_GENERATION_TESTS=1 "
            "(same opt-in gate as tests/statblocks_v1/integration/test_openai_generation.py)."
        )
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Refusing to call OpenAI: OPENAI_API_KEY is not set.")


def _provider_options() -> ProviderOptionsV1:
    settings = GenerationSettingsV1.from_environment()
    return ProviderOptionsV1(
        model=settings.model,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
    )


def _strip_schema_descriptions(node: Any) -> Any:
    """Remove schema-node ``description`` keys; preserve property names named description."""
    if isinstance(node, list):
        return [_strip_schema_descriptions(item) for item in node]
    if not isinstance(node, dict):
        return node

    transformed: dict[str, Any] = {}
    for key, value in node.items():
        if key == "description":
            continue
        if key == "properties" and isinstance(value, dict):
            # Property names are never treated as metadata keywords.
            transformed[key] = {
                prop_name: _strip_schema_descriptions(prop_schema)
                for prop_name, prop_schema in value.items()
            }
            continue
        if key in {"$defs", "definitions"} and isinstance(value, dict):
            transformed[key] = {
                def_name: _strip_schema_descriptions(def_schema)
                for def_name, def_schema in value.items()
            }
            continue
        transformed[key] = _strip_schema_descriptions(value)
    return transformed


def _compiled_schema_with_descriptions(*, keep_descriptions: bool) -> CompiledSchemaV1:
    base = compile_openai_definition_schema()
    schema = base.schema if keep_descriptions else _strip_schema_descriptions(copy.deepcopy(base.schema))
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return CompiledSchemaV1(
        name=base.name,
        schema=schema,
        compiler_version=SCHEMA_COMPILER_VERSION,
        fingerprint=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )


def _system_message(*, use_real_prompt: bool) -> str:
    return build_system_prompt("2024") if use_real_prompt else MINIMAL_SYSTEM


def _arm_config(arm: str) -> tuple[bool, bool]:
    """Return (keep_descriptions, use_real_system_prompt)."""
    if arm == "bare":
        return False, False
    if arm == "schema-only":
        return True, False
    if arm == "prompt-only":
        return False, True
    if arm == "both":
        return True, True
    raise ValueError(f"unknown arm: {arm}")


def _load_fixtures(fixture_name: str | None, description_file: Path | None) -> list[Fixture]:
    if description_file is not None:
        text = description_file.read_text(encoding="utf-8").strip()
        if not text:
            raise SystemExit(f"Description file is empty: {description_file}")
        return [
            Fixture(
                name=description_file.stem,
                name_hint=description_file.stem.replace("-", " ").replace("_", " ").title(),
                description=text,
            )
        ]

    if not FIXTURE_DIR.is_dir():
        raise SystemExit(f"Fixture directory missing: {FIXTURE_DIR}")

    fixtures: list[Fixture] = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        if fixture_name is not None and path.stem != fixture_name:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        name_hint = payload.get("name_hint")
        description = payload.get("description")
        if not isinstance(name_hint, str) or not name_hint.strip():
            raise SystemExit(f"Fixture {path.name} missing non-empty name_hint")
        if not isinstance(description, str) or not description.strip():
            raise SystemExit(f"Fixture {path.name} missing non-empty description")
        fixtures.append(Fixture(name=path.stem, name_hint=name_hint, description=description))

    if not fixtures:
        if fixture_name:
            raise SystemExit(f"No fixture named {fixture_name!r} under {FIXTURE_DIR}")
        raise SystemExit(f"No fixtures found under {FIXTURE_DIR}")
    return fixtures


def _build_command(fixture: Fixture) -> GenerateStatblockCommandV1:
    return GenerateStatblockCommandV1(
        request_id=f"prompt-eval-{uuid.uuid4().hex[:12]}",
        ruleset=RulesetRef(system=RulesetSystem.dnd5e, edition=RulesetEdition.edition_2024),
        source=SourceSnapshotV1(name_hint=fixture.name_hint, description=fixture.description),
        intent=GenerationIntentV1(),
        context=EncounterContextV1(),
        asset_options=AssetOptionsV1(),
        caller=CallerProvenanceV1(caller_scope="prompt-eval"),
    )


def _error_codes_from_definition(definition: StatblockDefinitionV1) -> list[str]:
    receipt = validate_definition(
        definition,
        ValidationMode.generation_candidate,
        validated_at=datetime.now(timezone.utc),
    )
    return sorted(
        {
            issue.code
            for issue in receipt.issues
            if issue.severity is ValidationSeverity.error
        }
    )


def _run_trial(
    *,
    provider: OpenAIDefinitionProvider,
    options: ProviderOptionsV1,
    fixture: Fixture,
    arm: str,
    trial: int,
) -> TrialResult:
    keep_descriptions, use_real_prompt = _arm_config(arm)
    schema = _compiled_schema_with_descriptions(keep_descriptions=keep_descriptions)
    system = _system_message(use_real_prompt=use_real_prompt)
    prompt = build_generation_prompt(_build_command(fixture))

    outcome = provider.generate_definition(
        prompt=prompt,
        system=system,
        schema=schema,
        options=options,
    )

    result = TrialResult(
        fixture=fixture.name,
        arm=arm,
        trial=trial,
        outcome_kind=outcome.kind.value,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        message=outcome.message,
    )

    if outcome.kind is not ProviderOutcomeKind.success or outcome.payload is None:
        return result

    try:
        definition = StatblockDefinitionV1.model_validate(outcome.payload)
    except ValidationError as exc:
        result.outcome_kind = "parse_failure"
        result.message = str(exc.errors()[0].get("msg", "model validation failed"))
        return result

    result.error_codes = _error_codes_from_definition(definition)
    return result


def _summarize_arm(results: list[TrialResult], arm: str) -> ArmSummary:
    summary = ArmSummary(arm=arm)
    for item in results:
        if item.arm != arm:
            continue
        summary.trials += 1
        if item.outcome_kind != ProviderOutcomeKind.success.value:
            summary.provider_failures[item.outcome_kind] += 1
            continue
        summary.api_calls += 1
        summary.total_input_tokens += item.input_tokens or 0
        summary.total_output_tokens += item.output_tokens or 0
        if not item.error_codes:
            summary.clean_trials += 1
        for code in item.error_codes:
            summary.error_code_counts[code] += 1
    return summary


def _print_arm_summary(summary: ArmSummary) -> None:
    clean_rate = summary.clean_trials / summary.trials if summary.trials else 0.0
    print(f"\n=== arm: {summary.arm} ===")
    print(f"trials: {summary.trials}")
    print(f"clean rate: {clean_rate:.2f} ({summary.clean_trials}/{summary.trials})")
    if summary.provider_failures:
        print("provider failures:")
        for kind, count in summary.provider_failures.most_common():
            print(f"  {kind}: {count}")
    else:
        print("provider failures: none")
    if summary.error_code_counts:
        print("error code frequency (descending):")
        for code, count in summary.error_code_counts.most_common():
            print(f"  {code}: {count}")
    else:
        print("error code frequency: (none)")
    print(
        "tokens: "
        f"input={summary.total_input_tokens} "
        f"output={summary.total_output_tokens} "
        f"({summary.api_calls} successful calls)"
    )


def _estimate_calls(fixtures: list[Fixture], arms: list[str], trials: int) -> int:
    return len(fixtures) * len(arms) * trials


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure domain-validator error codes across prompt/schema ablation arms."
    )
    parser.add_argument(
        "--arm",
        choices=[*ALL_ARMS, "all"],
        default="both",
        help="Ablation arm to run (default: both = shipping config).",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=5,
        help="Trials per (fixture, arm) pair (default: 5).",
    )
    parser.add_argument(
        "--fixture",
        help="Run only the committed fixture with this stem name.",
    )
    parser.add_argument(
        "--description-file",
        type=Path,
        help="Run arbitrary local prose instead of committed fixtures.",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write raw per-trial results to this JSON file.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm live OpenAI calls when the plan exceeds 20 API calls.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.trials < 1:
        raise SystemExit("--trials must be >= 1")
    if args.fixture and args.description_file:
        raise SystemExit("Use either --fixture or --description-file, not both.")

    _load_environment()

    arms = list(ALL_ARMS) if args.arm == "all" else [args.arm]
    fixtures = _load_fixtures(args.fixture, args.description_file)
    planned_calls = _estimate_calls(fixtures, arms, args.trials)

    settings = GenerationSettingsV1.from_environment()
    print("statblock prompt/schema falsification harness")
    print(f"model: {settings.model}")
    print(f"fixtures: {', '.join(f.name for f in fixtures)}")
    print(f"arms: {', '.join(arms)}")
    print(f"trials per (fixture, arm): {args.trials}")
    print(f"estimated API calls: {planned_calls}")

    if planned_calls > 20 and not args.yes:
        print(
            f"\nPlanned {planned_calls} live API calls (>20). "
            "Re-run with --yes to proceed."
        )
        return

    _require_live_env()

    provider = OpenAIDefinitionProvider()
    options = _provider_options()
    all_results: list[TrialResult] = []

    for fixture in fixtures:
        for arm in arms:
            for trial in range(1, args.trials + 1):
                print(
                    f"\n--- {fixture.name} / {arm} / trial {trial}/{args.trials} ---",
                    flush=True,
                )
                result = _run_trial(
                    provider=provider,
                    options=options,
                    fixture=fixture,
                    arm=arm,
                    trial=trial,
                )
                all_results.append(result)
                if result.outcome_kind == ProviderOutcomeKind.success.value:
                    codes = ", ".join(result.error_codes) if result.error_codes else "(clean)"
                    print(f"outcome: success | error codes: {codes}")
                else:
                    print(f"outcome: {result.outcome_kind} | {result.message or ''}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for arm in arms:
        _print_arm_summary(_summarize_arm(all_results, arm))

    total_input = sum(r.input_tokens or 0 for r in all_results if r.outcome_kind == "success")
    total_output = sum(r.output_tokens or 0 for r in all_results if r.outcome_kind == "success")
    successful = sum(1 for r in all_results if r.outcome_kind == "success")
    print(
        f"\ntotal token spend: input={total_input} output={total_output} "
        f"across {successful} successful calls"
    )

    if args.json:
        payload = [asdict(item) for item in all_results]
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote per-trial JSON: {args.json}")


if __name__ == "__main__":
    main(sys.argv[1:])
