from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

from statblocks_v1 import CONTRACT_NAME, CONTRACT_VERSION
from statblocks_v1.api.models import (
    AppendRevisionRequestV1,
    CreateStatblockRequestV1,
    CreateStatblockResponseV1,
    ErrorEnvelopeV1,
    GenerateCandidateRequestV1,
    ValidateDefinitionRequestV1,
    ValidationResponseV1,
)
from statblocks_v1.domain.resources import GeneratedStatblockCandidateV1, StatblockRevisionResourceV1

ROOT = Path(__file__).parents[2]
ARTIFACT = ROOT / "openapi" / "dungeonbuddy-statblocks-v1.json"
TYPESCRIPT = ROOT / "generated" / "dungeonbuddy-statblocks-v1" / "client.ts"
FIXTURES = ROOT / "Docs" / "Design" / "fixtures" / "dungeonbuddy-statblock-v1-api"
_TS_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _export_module():
    spec = importlib.util.spec_from_file_location(
        "export_dungeonbuddy_statblock_openapi",
        ROOT / "scripts" / "export_dungeonbuddy_statblock_openapi.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_openapi_artifact_and_generated_types_are_current() -> None:
    exporter = _export_module()
    schema = exporter.build_openapi()
    expected_openapi = exporter.serialize_openapi(schema)
    expected_typescript = exporter.render_typescript(schema)

    assert ARTIFACT.read_text(encoding="utf-8") == expected_openapi
    assert TYPESCRIPT.read_text(encoding="utf-8") == expected_typescript
    fingerprint = f"sha256:{hashlib.sha256(expected_openapi.encode()).hexdigest()}"
    assert f"// Source fingerprint: {fingerprint}" in expected_typescript
    assert "export type " in expected_typescript
    assert "-" not in {
        line.split("export type ", 1)[1].split(" ", 1)[0]
        for line in expected_typescript.splitlines()
        if line.startswith("export type ")
    }
    assert " | unknown" not in expected_typescript
    assert "?: unknown" not in expected_typescript
    assert "unit?: DistanceUnit" in expected_typescript
    assert 'contract: "dungeonmind.dungeonbuddy-statblocks"' in expected_typescript
    assert 'contract_version: "1.0.0"' in expected_typescript
    assert 'contract?: "dungeonmind.dungeonbuddy-statblocks"' not in expected_typescript
    assert 'contract_version?: "1.0.0"' not in expected_typescript
    for line in expected_typescript.splitlines():
        if line.startswith("export type "):
            name = line.split("export type ", 1)[1].split(" ", 1)[0]
            assert _TS_IDENT.match(name), name

    openapi = json.loads(expected_openapi)
    for schema_name in (
        "GeneratedStatblockCandidateV1",
        "StatblockRevisionResourceV1",
        "HealthResponseV1",
    ):
        required = set(openapi["components"]["schemas"][schema_name]["required"])
        assert {"contract", "contract_version"} <= required, schema_name

    paths = openapi["paths"]
    operations = {
        operation["operationId"]
        for path in paths.values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert {
        "generate_statblock_candidate_v1",
        "revise_statblock_candidate_v1",
        "validate_statblock_definition_v1",
        "get_statblock_candidate_v1",
        "create_statblock_v1",
        "append_statblock_revision_v1",
        "get_statblock_v1",
        "list_statblock_revisions_v1",
        "get_statblock_revision_v1",
    } <= operations
    assert any(
        name.startswith("AssetBindingV1") for name in openapi["components"]["schemas"]
    )


def test_contract_identity_rejects_missing_and_incorrect_values(load_fixture) -> None:
    from datetime import datetime, timezone

    import pytest
    from pydantic import ValidationError

    from statblocks_v1.api.models import HealthResponseV1
    from statblocks_v1.domain.receipts import ValidationMode
    from statblocks_v1.domain.rule_elements import StatblockDefinitionV1
    from statblocks_v1.domain.validation import validate_definition

    definition = StatblockDefinitionV1.model_validate(load_fixture("simple_bruiser"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    receipt = validate_definition(
        definition, ValidationMode.generation_candidate, validated_at=now
    )
    base_candidate = {
        "candidate_id": "cand_identity1",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "definition": definition.model_dump(mode="json"),
        "validation_receipt": receipt.model_dump(mode="json"),
        "created_at": now.isoformat(),
        "expires_at": now.isoformat(),
    }
    base_revision = {
        "statblock_id": "sb_identity1",
        "revision_id": "rev_identity1",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "definition": definition.model_dump(mode="json"),
        "canonical_definition": "{}",
        "definition_digest": "sha256:" + ("0" * 64),
        "validation_receipt": receipt.model_dump(mode="json"),
        "created_at": now.isoformat(),
    }
    base_health = {
        "status": "ok",
        "contract": CONTRACT_NAME,
        "contract_version": CONTRACT_VERSION,
        "capabilities": [],
    }

    for model, payload, drop_key in (
        (GeneratedStatblockCandidateV1, base_candidate, "contract"),
        (GeneratedStatblockCandidateV1, base_candidate, "contract_version"),
        (StatblockRevisionResourceV1, base_revision, "contract"),
        (StatblockRevisionResourceV1, base_revision, "contract_version"),
        (HealthResponseV1, base_health, "contract"),
        (HealthResponseV1, base_health, "contract_version"),
    ):
        missing = {key: value for key, value in payload.items() if key != drop_key}
        with pytest.raises(ValidationError):
            model.model_validate(missing)

    for model, payload, field, bad in (
        (GeneratedStatblockCandidateV1, base_candidate, "contract", "other.contract"),
        (GeneratedStatblockCandidateV1, base_candidate, "contract_version", "9.9.9"),
        (StatblockRevisionResourceV1, base_revision, "contract", "other.contract"),
        (StatblockRevisionResourceV1, base_revision, "contract_version", "9.9.9"),
        (HealthResponseV1, base_health, "contract", "other.contract"),
        (HealthResponseV1, base_health, "contract_version", "9.9.9"),
    ):
        wrong = {**payload, field: bad}
        with pytest.raises(ValidationError):
            model.model_validate(wrong)


def test_published_api_fixtures_match_live_route_semantics() -> None:
    from statblocks_v1.application.generation import _digest_text

    load = lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    generate_request = load("generate-request.json")
    GenerateCandidateRequestV1.model_validate(generate_request)
    candidate = GeneratedStatblockCandidateV1.model_validate(load("candidate-response.json"))
    ValidateDefinitionRequestV1.model_validate(load("validate-request.json"))
    validate_response = ValidationResponseV1.model_validate(load("validate-response.json"))
    CreateStatblockRequestV1.model_validate(load("create-request.json"))
    create_response = CreateStatblockResponseV1.model_validate(load("create-response.json"))
    AppendRevisionRequestV1.model_validate(load("append-request.json"))
    revision = StatblockRevisionResourceV1.model_validate(load("exact-revision-response.json"))
    error = ErrorEnvelopeV1.model_validate(load("errors.json"))

    assert "actor" not in generate_request
    assert "asset_options" not in generate_request
    assert candidate.contract == CONTRACT_NAME
    assert candidate.contract_version == CONTRACT_VERSION
    assert candidate.validation_receipt.mode.value == "generation_candidate"
    assert candidate.generation_receipt is not None
    assert candidate.generation_receipt.request_id == generate_request["request_id"]
    assert candidate.generation_receipt.caller_scope == "dungeonbuddy"
    assert candidate.generation_receipt.actor is None
    assert candidate.generation_receipt.source_description_digest == _digest_text(
        generate_request["source"]["description"]
    )
    assert candidate.assets == []
    assert candidate.asset_brief is not None
    assert candidate.asset_brief.prompt == generate_request["source"]["description"]
    assert validate_response.validation_receipt.mode.value == "editor_preview"
    assert revision.contract == CONTRACT_NAME
    assert revision.contract_version == CONTRACT_VERSION
    assert revision.validation_receipt.mode.value == "persistence"
    assert create_response.revision.validation_receipt.mode.value == "persistence"
    assert error.error.code == "validation_failed"
    assert error.error.details is not None
    assert error.error.details["is_persistence_ready"] is False
    assert "validation_receipt" in error.error.details
    assert error.error.details["validation_receipt"]["mode"] == "persistence"
