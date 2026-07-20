"""Route-presence smoke tests for preserved legacy StatBlockGenerator paths."""

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from routers import statblockgenerator_router


def test_legacy_router_keeps_expected_paths_and_one_health_route():
    routes = {
        (route.path, next(iter(route.methods)))
        for route in statblockgenerator_router.router.routes
        if isinstance(route, APIRoute)
    }

    assert {
        ("/api/statblockgenerator/health", "GET"),
        ("/api/statblockgenerator/generate-statblock", "POST"),
        ("/api/statblockgenerator/upload-image", "POST"),
        ("/api/statblockgenerator/upload-images", "POST"),
        ("/api/statblockgenerator/validate-statblock", "POST"),
        ("/api/statblockgenerator/calculate-cr", "POST"),
        ("/api/statblockgenerator/create-project", "POST"),
        ("/api/statblockgenerator/list-projects", "GET"),
        ("/api/statblockgenerator/list-all-images", "GET"),
        ("/api/statblockgenerator/project/{project_id}", "GET"),
        ("/api/statblockgenerator/project/{project_id}/image/{image_id}", "DELETE"),
        ("/api/statblockgenerator/delete-image", "DELETE"),
        ("/api/statblockgenerator/project/{project_id}", "DELETE"),
        ("/api/statblockgenerator/save-project", "POST"),
        ("/api/statblockgenerator/save-session", "POST"),
        ("/api/statblockgenerator/load-session/{session_id}", "GET"),
    }.issubset(routes)
    assert not any(path.startswith("/api/statblockgenerator/v2/") for path, _ in routes)


def test_legacy_health_preserves_the_first_registered_response_shape(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FAL_KEY", raising=False)
    app = FastAPI()
    app.include_router(statblockgenerator_router.router)

    response = TestClient(app).get("/api/statblockgenerator/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "statblockgenerator",
        "generator_ready": True,
        "openai_configured": False,
        "fal_configured": False,
    }
