import os
import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Add the parent directory of DungeonMind to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

os.environ["TESTING"] = "1"
os.environ["ENVIRONMENT"] = "testing"

from DungeonMind.app import app

@pytest.fixture
def test_app():
    with TestClient(app) as client:
        yield client

@pytest.fixture(autouse=True)
def debug_info(request):
    print(f"\nRunning test: {request.node.name}")
    print(f"TESTING env var: {os.environ.get('TESTING')}")
    print(f"ENVIRONMENT env var: {os.environ.get('ENVIRONMENT')}")
