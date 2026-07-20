"""Production app.py import / mount smoke for PR21 legacy quarantine.

These tests intentionally import the real production ``app`` module so they
catch duplicate route registration, shared-generator construction, and mount
order issues that minimal FastAPI() fixtures cannot see.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from routers.internal_auth import INTERNAL_KEY_ENV, INTERNAL_KEY_HEADER

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_production_app_mounts_legacy_and_v2_once_with_shared_generator(monkeypatch):
    monkeypatch.setenv(INTERNAL_KEY_ENV, "prod-smoke-internal-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)

    from app import app as production_app
    from routers import statblock_v2_compatibility_router, statblockgenerator_router
    from statblockgenerator.runtime import get_statblock_generator

    # app.py rebinds both router modules to the shared factory instance on import.
    assert (
        statblockgenerator_router.statblock_generator
        is statblock_v2_compatibility_router.statblock_generator
    )
    assert (
        statblockgenerator_router.statblock_generator is get_statblock_generator()
    )

    routes = [
        (route.path, method)
        for route in production_app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    ]
    assert routes.count(("/api/statblockgenerator/health", "GET")) == 1
    assert routes.count(("/api/statblockgenerator/v2/health", "GET")) == 1
    assert routes.count(("/api/statblockgenerator/generate-statblock", "POST")) == 1
    assert routes.count(("/api/statblockgenerator/v2/generate-draft", "POST")) == 1
    assert routes.count(("/api/statblockgenerator/v2/render-draft", "POST")) == 1
    assert ("/api/internal/dungeonbuddy/v1/statblocks/health/live", "GET") in routes

    client = TestClient(
        production_app, base_url="http://localhost", headers={"host": "localhost"}
    )
    legacy = client.get("/api/statblockgenerator/health")
    assert legacy.status_code == 200
    assert legacy.json()["service"] == "statblockgenerator"
    assert "contract" not in legacy.json()

    v2 = client.get(
        "/api/statblockgenerator/v2/health",
        headers={INTERNAL_KEY_HEADER: "prod-smoke-internal-key"},
    )
    assert v2.status_code == 200
    assert v2.json()["contract"] == "command_board_draft_v2"


def test_pr21_artifacts_are_gitignored():
    ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.egg-info/" in ignore
    assert ".VSCodeCounter/" in ignore

    checked = subprocess.run(
        ["git", "check-ignore", "-v", ".VSCodeCounter/x", "dungeonmind.egg-info/PKG-INFO"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert ".VSCodeCounter" in checked.stdout
    assert "egg-info" in checked.stdout


def test_pr21_authority_docs_exist():
    required = (
        "Docs/Design/DESIGN-dungeonbuddy-statblock-contract-v1.md",
        "Docs/Design/AUDIT-dungeonbuddy-statblock-v1-route-readiness.md",
        "Docs/Plans/PLAN-dungeonbuddy-statblock-v1-route-roadmap.md",
        "Docs/Design/AUDIT-statblock-legacy-consumers.md",
        "Docs/Design/AUDIT-dungeonmindserver-remaining-architecture-debt.md",
        "Docs/Plans/HANDOFF-pr21-statblock-legacy-quarantine-repo-hygiene.md",
        "README.md",
    )
    for relative in required:
        path = REPO_ROOT / relative
        assert path.is_file(), f"missing authority doc {relative}"
        assert path.stat().st_size > 0
