"""Root pytest fixtures — env stubs before any app import."""

from __future__ import annotations

import logging
import os

import pytest

# Stub required secrets before importing app / session_config / OAuth / SMS.
os.environ.setdefault("SESSION_SECRET_KEY", "pytest-session-secret-key-not-for-prod")
os.environ.setdefault("GOOGLE_CLIENT_ID", "pytest-google-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "pytest-google-client-secret")
os.environ.setdefault("EXTERNAL_MESSAGE_API_KEY", "pytest-external-message-key")
os.environ.setdefault("EXTERNAL_SMS_ENDPOINT", "https://example.test/sms-forward")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACpytest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "pytest-twilio-token")
os.environ.setdefault("TWILIO_TEST_MODE", "false")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ALLOWED_HOSTS", "localhost,testserver,127.0.0.1")
os.environ.setdefault("REACT_LANDING_URL", "http://localhost:3000")
os.environ.setdefault("DUNGEONMIND_API_URL", "http://localhost:7860")
os.environ.setdefault("OPENAI_API_KEY", "pytest-openai-key-not-for-prod")
os.environ.setdefault("CLOUDFLARE_ACCOUNT_ID", "pytest-cloudflare-account-id")
os.environ.setdefault("CLOUDFLARE_IMAGES_API_TOKEN", "pytest-cloudflare-images-token")
os.environ.setdefault("R2_ACCESS_KEY_ID", "pytest-r2-access-key")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "pytest-r2-secret-key")
os.environ.setdefault("R2_BUCKET_NAME", "pytest-r2-bucket")
os.environ.setdefault("FIREBASE_SKIP_INIT", "true")
os.environ.setdefault("TRUST_PROXY", "false")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture(scope="session")
def test_app():
    """
    Build the FastAPI app with Firestore stubbed when credentials are absent
    (CI / FIREBASE_SKIP_INIT), so security route tests can exercise auth gates.
    """
    from unittest.mock import MagicMock

    if os.getenv("FIREBASE_SKIP_INIT", "").lower() in ("1", "true", "yes"):
        import firestore.firebase_config as fc

        stub = MagicMock(name="firestore_db_stub")
        fc.db = stub
        # Also patch modules that already imported db by reference where possible
        try:
            import firestore.firestore_utils as fu

            fu.db = stub
        except Exception:
            pass

    from app import create_app

    logger.debug("Setting up test app via create_app()")
    return create_app()


@pytest.fixture(scope="session")
def test_client(test_app):
    from fastapi.testclient import TestClient

    logger.debug("Creating test client with localhost base URL")
    return TestClient(
        test_app,
        base_url="http://localhost",
        headers={"host": "localhost"},
    )


@pytest.fixture(scope="function")
def session_manager():
    from session_management import EnhancedGlobalSessionManager

    return EnhancedGlobalSessionManager(session_timeout_hours=1)


logger.debug("conftest.py loaded")
