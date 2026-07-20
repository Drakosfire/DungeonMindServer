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
    for line in expected_typescript.splitlines():
        if line.startswith("export type "):
            name = line.split("export type ", 1)[1].split(" ", 1)[0]
            assert _TS_IDENT.match(name), name

    paths = json.loads(expected_openapi)["paths"]
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
        name.startswith("AssetBindingV1")
        for name in json.loads(expected_openapi)["components"]["schemas"]
    )


def test_published_api_fixtures_match_live_route_semantics() -> None:
    load = lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    GenerateCandidateRequestV1.model_validate(load("generate-request.json"))
    candidate = GeneratedStatblockCandidateV1.model_validate(load("candidate-response.json"))
    ValidateDefinitionRequestV1.model_validate(load("validate-request.json"))
    validate_response = ValidationResponseV1.model_validate(load("validate-response.json"))
    CreateStatblockRequestV1.model_validate(load("create-request.json"))
    create_response = CreateStatblockResponseV1.model_validate(load("create-response.json"))
    AppendRevisionRequestV1.model_validate(load("append-request.json"))
    revision = StatblockRevisionResourceV1.model_validate(load("exact-revision-response.json"))
    error = ErrorEnvelopeV1.model_validate(load("errors.json"))

    assert candidate.contract == CONTRACT_NAME
    assert candidate.contract_version == CONTRACT_VERSION
    assert candidate.validation_receipt.mode.value == "generation_candidate"
    assert validate_response.validation_receipt.mode.value == "editor_preview"
    assert revision.contract == CONTRACT_NAME
    assert revision.contract_version == CONTRACT_VERSION
    assert revision.validation_receipt.mode.value == "persistence"
    assert create_response.revision.validation_receipt.mode.value == "persistence"
    assert error.error.code == "validation_failed"
