from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

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
    expected = exporter.serialize_openapi(exporter.build_openapi())

    assert ARTIFACT.read_text(encoding="utf-8") == expected
    fingerprint = f"sha256:{hashlib.sha256(expected.encode()).hexdigest()}"
    assert f"// Source fingerprint: {fingerprint}" in TYPESCRIPT.read_text(encoding="utf-8")
    paths = json.loads(expected)["paths"]
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
        for name in json.loads(expected)["components"]["schemas"]
    )


def test_published_api_fixtures_validate_against_authoritative_models() -> None:
    load = lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    GenerateCandidateRequestV1.model_validate(load("generate-request.json"))
    GeneratedStatblockCandidateV1.model_validate(load("candidate-response.json"))
    ValidateDefinitionRequestV1.model_validate(load("validate-request.json"))
    ValidationResponseV1.model_validate(load("validate-response.json"))
    CreateStatblockRequestV1.model_validate(load("create-request.json"))
    CreateStatblockResponseV1.model_validate(load("create-response.json"))
    AppendRevisionRequestV1.model_validate(load("append-request.json"))
    StatblockRevisionResourceV1.model_validate(load("exact-revision-response.json"))
    ErrorEnvelopeV1.model_validate(load("errors.json"))
