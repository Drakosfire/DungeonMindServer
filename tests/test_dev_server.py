from unittest.mock import Mock

import pytest

import dev_server


@pytest.mark.parametrize(
    "configured, expected", [(None, 7860), ("17860", 17860), ("1", 1), ("65535", 65535)]
)
def test_entrypoint_passes_configured_port_to_uvicorn(
    monkeypatch, capsys, configured, expected
):
    if configured is None:
        monkeypatch.delenv("DUNGEONMIND_SERVER_PORT", raising=False)
    else:
        monkeypatch.setenv("DUNGEONMIND_SERVER_PORT", configured)
    run = Mock()
    monkeypatch.setattr(dev_server.uvicorn, "run", run)

    dev_server.main()

    run.assert_called_once()
    args, kwargs = run.call_args
    assert args == ("app:app",)
    assert kwargs["port"] == expected
    assert kwargs["host"] == "0.0.0.0"
    assert kwargs["reload"] is True
    assert kwargs["reload_dirs"] == [
        "routers",
        "cardgenerator",
        "cloudflare",
        "cloudflareR2",
        "firestore",
        "ruleslawyer",
        "storegenerator",
        "sms",
        "mapgenerator",
    ]
    assert kwargs["log_level"] == "info"
    output = capsys.readouterr().out
    assert f"http://localhost:{expected}" in output
    assert f"http://localhost:{expected}/health" in output


@pytest.mark.parametrize(
    "configured", ["", "not-a-port", "0", "-1", "65536", "17860.5"]
)
def test_invalid_port_fails_before_binding(monkeypatch, configured):
    monkeypatch.setenv("DUNGEONMIND_SERVER_PORT", configured)
    run = Mock()
    monkeypatch.setattr(dev_server.uvicorn, "run", run)

    with pytest.raises(
        SystemExit,
        match="DUNGEONMIND_SERVER_PORT must be an integer between 1 and 65535",
    ):
        dev_server.main()

    run.assert_not_called()
