import sys
import os
from pathlib import Path

# Add the parent directory of DungeonMind to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
# import HTTPException
from fastapi import HTTPException
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from DungeonMind.app import app

client = TestClient(app)

def test_current_user_unauthenticated():
    response = client.get("/auth/current-user")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

@patch('DungeonMind.auth_router.get_current_user')
def test_current_user_authenticated(mock_get_current_user):
    mock_user = {
        "iss": "https://accounts.google.com",
        "sub": "123",
        "name": "Test User",
        "email": "test@example.com",
        "picture": "https://example.com/photo.jpg"
    }
    mock_get_current_user.return_value = mock_user

    response = client.get("/auth/current-user")
    assert response.status_code == 200
    assert response.json() == mock_user

@patch('DungeonMind.auth_router.get_current_user')
def test_current_user_expired_session(mock_get_current_user):
    mock_get_current_user.side_effect = HTTPException(status_code=401, detail="Session expired")

    response = client.get("/auth/current-user")
    assert response.status_code == 401
    assert response.json() == {"detail": "Session expired"}

@patch('DungeonMind.auth_router.get_current_user')
def test_current_user_missing_exp(mock_get_current_user):
    mock_user = {
        "iss": "https://accounts.google.com",
        "sub": "123",
        "name": "Test User",
        "email": "test@example.com",
        "picture": "https://example.com/photo.jpg"
    }
    mock_get_current_user.return_value = mock_user

    response = client.get("/auth/current-user")
    print(f"Response status code: {response.status_code}")
    print(f"Response content: {response.content}")
    assert response.status_code == 200
    assert response.json() == mock_user
