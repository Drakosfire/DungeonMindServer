from __future__ import annotations

from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import INTERNAL_KEY_HEADER
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
    assert response.json()["status"] == "not_ready"
    assert response.json()["errors"] == ["openai_not_configured"]
    assert "secret-not-logged" not in response.text


def test_feature_flag_keeps_reads_and_closes_generation(monkeypatch, auth_headers) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("STATBLOCKS_V1_FEATURE_ENABLED", "false")
    client = TestClient(create_test_app())
    capability = client.get(PREFIX, headers=auth_headers)
    generation = client.post(
        "/api/internal/dungeonbuddy/v1/statblock-candidates:generate",
        headers=auth_headers, json={"not": "a valid body"},
    )
    assert "candidate_generate" not in capability.json()["capabilities"]
    assert capability.json()["status"] == "available"
    assert generation.status_code == 503
    assert generation.json()["error"]["code"] == "generation_disabled"
