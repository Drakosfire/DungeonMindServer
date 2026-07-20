from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from statblocks_v1.api.dependencies import INTERNAL_KEY_HEADER
from statblocks_v1.observability import REQUEST_ID_HEADER, safe_fields
from statblocks_v1.testing import create_test_app


def test_safe_fields_redacts_payloads_and_keys() -> None:
    assert safe_fields(
        request_id="req_1",
        prompt="private",
        definition={"name": "secret"},
        api_key="key",
    ) == {"request_id": "req_1"}


def test_request_log_has_correlation_and_no_body(caplog, auth_headers, monkeypatch) -> None:
    monkeypatch.setenv("DUNGEONBUDDY_INTERNAL_API_KEY", auth_headers[INTERNAL_KEY_HEADER])
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    caplog.set_level(logging.INFO, logger="statblocks_v1")
    response = TestClient(create_test_app()).get(
        "/api/internal/dungeonbuddy/v1/statblocks/health",
        headers={**auth_headers, REQUEST_ID_HEADER: "req_private"},
    )
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "req_private"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "req_private" in messages
    assert "campaign-private-description" not in messages
    assert auth_headers[INTERNAL_KEY_HEADER] not in messages
    assert "test-openai-key" not in messages
