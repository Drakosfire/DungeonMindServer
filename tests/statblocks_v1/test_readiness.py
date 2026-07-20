from __future__ import annotations

from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import INTERNAL_KEY_HEADER
from statblocks_v1.api.health import configure_composition_probe
from statblocks_v1.testing import create_test_app

PREFIX = "/api/internal/dungeonbuddy/v1/statblocks/health"


def test_liveness_is_public_and_readiness_is_authenticated(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "test-key")
    client = TestClient(create_test_app())
    assert client.get(f"{PREFIX}/live").json() == {"status": "live"}
    assert client.get(f"{PREFIX}/ready").status_code == 401


def test_readiness_reports_missing_provider_without_secret(monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", "secret-not-logged")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = TestClient(create_test_app()).get(
        f"{PREFIX}/ready", headers={INTERNAL_KEY_HEADER: "secret-not-logged"}
    )
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["errors"] == ["openai_not_configured"]
    assert body["generation_enabled"] is False
    assert "secret-not-logged" not in response.text


def test_capabilities_omit_generation_when_openai_missing(monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = TestClient(create_test_app()).get(PREFIX, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "available"
    assert "candidate_generate" not in body["capabilities"]
    assert "statblock_read" in body["capabilities"]


def test_misconfigured_settings_advertise_no_capabilities(monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("STATBLOCKS_V1_FEATURE_ENABLED", "not-a-bool")
    response = TestClient(create_test_app()).get(PREFIX, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "misconfigured"
    assert response.json()["capabilities"] == []


def test_feature_flag_keeps_reads_and_closes_generation(monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("STATBLOCKS_V1_FEATURE_ENABLED", "false")
    client = TestClient(create_test_app())
    capability = client.get(PREFIX, headers=auth_headers)
    generation = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        headers=auth_headers,
        json={"not": "a valid body"},
    )
    assert "candidate_generate" not in capability.json()["capabilities"]
    assert capability.json()["status"] == "available"
    assert generation.status_code == 503
    assert generation.json()["error"]["code"] == "generation_disabled"


def test_readiness_includes_composition_probe_errors(monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    configure_composition_probe(lambda _settings: ["firestore_client_unconfigured"])
    try:
        response = TestClient(create_test_app()).get(PREFIX + "/ready", headers=auth_headers)
    finally:
        configure_composition_probe(None)
    assert response.status_code == 503
    assert "firestore_client_unconfigured" in response.json()["errors"]


def test_readiness_openapi_declares_typed_payload(client: TestClient) -> None:
    schema = client.app.openapi()
    ready = schema["paths"][f"{PREFIX}/ready"]["get"]
    assert ready["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ReadinessResponseV1"
    )
    assert "ReadinessResponseV1" in schema["components"]["schemas"]


def test_capabilities_omit_generation_when_firestore_disabled(
    monkeypatch, auth_headers
) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("STATBLOCKS_V1_FIRESTORE_ENABLED", "false")
    response = TestClient(create_test_app()).get(PREFIX, headers=auth_headers)
    body = response.json()
    assert "candidate_generate" not in body["capabilities"]
    assert "statblock_read" not in body["capabilities"]


def test_assets_enabled_without_pipeline_closes_generation(
    monkeypatch, auth_headers
) -> None:
    from statblocks_v1.application.composition_state import set_asset_pipeline_ready

    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("STATBLOCKS_V1_ASSET_GATEWAY_ENABLED", "true")
    set_asset_pipeline_ready(False)
    client = TestClient(create_test_app())
    capability = client.get(PREFIX, headers=auth_headers)
    generation = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        headers=auth_headers,
        json={"not": "a valid body"},
    )
    assert "candidate_generate" not in capability.json()["capabilities"]
    assert generation.status_code == 503
    assert generation.json()["error"]["code"] == "internal_service_misconfigured"
