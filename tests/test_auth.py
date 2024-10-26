import sys
import os
from pathlib import Path
import pytest

# Add the parent directory of DungeonMind to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
# import HTTPException
from fastapi import HTTPException, Depends

from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from DungeonMind.app import app
from DungeonMind.auth_router import get_current_user_dependency

client = TestClient(app, base_url="http://testserver")

@pytest.fixture
def test_app():
    with TestClient(app) as client:
        yield client

def override_get_current_user():
    return {
        "iss": "https://accounts.google.com",
        "sub": "123",
        "name": "Test User",
        "email": "test@example.com",
        "picture": "https://example.com/photo.jpg"
    }

def test_current_user_unauthenticated(test_app):
    response = test_app.get("/auth/current-user")
    assert response.status_code == 401

def test_current_user_authenticated(test_app):
    app.dependency_overrides[get_current_user_dependency] = lambda: override_get_current_user

    response = test_app.get("/auth/current-user")
    assert response.status_code == 200
    assert response.json() == override_get_current_user()

    # Clean up the override
    app.dependency_overrides = {}

def test_current_user_expired_session(test_app):
    def expired_user():
        raise HTTPException(status_code=401, detail="Session expired")

    app.dependency_overrides[get_current_user_dependency] = expired_user

    response = test_app.get("/auth/current-user")
    assert response.status_code == 401

    # Clean up the override
    app.dependency_overrides = {}

def test_current_user_missing_exp(test_app):
    app.dependency_overrides[get_current_user_dependency] = lambda: override_get_current_user

    response = test_app.get("/auth/current-user")
    assert response.status_code == 200
    assert response.json() == override_get_current_user()

    # Clean up the override
    app.dependency_overrides = {}

def test_minimal(test_app):
    response = test_app.get("/")
    print(f"Response status: {response.status_code}")
    print(f"Response content: {response.content}")
    assert response.status_code != 400

def test_app_configuration(test_app):
    response = test_app.get("/health")
    print(f"Health check response: {response.status_code}, {response.content}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_app_loaded(test_app):
    assert test_app is not None
    response = test_app.get("/health")
    print(f"Health check response: {response.status_code}, {response.content}")
    assert response.status_code == 200

def test_cors(test_app):
    headers = {
        "Origin": "http://testserver",
        "Access-Control-Request-Method": "GET",
    }
    response = test_app.options("/", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
