"""Shared test helpers for statblock page routing and Firestore fakes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional
import json
import os
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from models.dungeonmind_objects import StatblockPageResponse


_SUPPORT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SUPPORT_DIR.parent
_GENERATED_DIR = _SUPPORT_DIR / "_generated"


def ensure_service_account_file() -> str:
    """Guarantee a Firebase service account JSON for local tests."""

    _GENERATED_DIR.mkdir(exist_ok=True)
    account_path = _GENERATED_DIR / "serviceAccountKey.json"

    if not account_path.exists():
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        service_account = {
            "type": "service_account",
            "project_id": "dungeonmind-test",
            "private_key_id": "test-key-id",
            "private_key": private_key_pem,
            "client_email": "test@dungeonmind-test.iam.gserviceaccount.com",
            "client_id": "1234567890",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/test@dungeonmind-test.iam.gserviceaccount.com",
        }

        account_path.write_text(json.dumps(service_account))

    os.environ.setdefault("SERVICE_ACCOUNT_PATH", str(account_path))
    return str(account_path)


def apply_statblock_env(monkeypatch) -> None:
    """Set environment variables so the FastAPI app boots under tests."""

    service_account = ensure_service_account_file()
    monkeypatch.setenv("SERVICE_ACCOUNT_PATH", service_account)
    monkeypatch.setenv("STATIC_ROOT", str(_PROJECT_ROOT / "static"))
    monkeypatch.setenv("SAVED_DATA_ROOT", str(_PROJECT_ROOT / "saved_data"))


def reset_statblock_env(monkeypatch) -> None:
    """Remove environment overrides previously set for statblock tests."""

    monkeypatch.delenv("SERVICE_ACCOUNT_PATH", raising=False)
    monkeypatch.delenv("STATIC_ROOT", raising=False)
    monkeypatch.delenv("SAVED_DATA_ROOT", raising=False)


class FakeStatblockDB:
    """In-memory stand-in for `DungeonMindObjectsDB` statblock operations."""

    def __init__(self) -> None:
        self.storage: Dict[str, StatblockPageResponse] = {}
        self._custom_get: Optional[Callable] = None
        self._custom_update: Optional[Callable] = None

    async def create_statblock_page(self, request, user_id: str) -> StatblockPageResponse:
        page_id = request.page.id or str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()
        response = StatblockPageResponse(
            objectId=page_id,
            name=request.name,
            description=request.description,
            tags=request.tags,
            visibility=request.visibility,
            createdAt=timestamp,
            updatedAt=timestamp,
            ownerId=user_id,
            projectId=request.metadata.projectId,
            worldId=request.metadata.worldId,
            page=request.page,
            statblockDetails=request.statblockDetails or {},
        )
        self.storage[page_id] = response
        return response

    async def get_statblock_page(self, page_id: str, user_id: str):  # noqa: D401
        return self.storage.get(page_id)

    def with_behaviour(
        self,
        *,
        get: Optional[Callable] = None,
        update: Optional[Callable] = None,
    ) -> "FakeStatblockDB":
        self._custom_get = get
        self._custom_update = update
        return self

    async def update_statblock_page(self, page_id: str, user_id: str, updates):
        existing = self.storage.get(page_id)
        if not existing:
            return None

        update_fields = {}
        if updates.name is not None:
            update_fields["name"] = updates.name
        if updates.description is not None:
            update_fields["description"] = updates.description
        if updates.tags is not None:
            update_fields["tags"] = updates.tags
        if updates.visibility is not None:
            update_fields["visibility"] = updates.visibility
        if updates.page is not None:
            update_fields["page"] = updates.page
        if updates.statblockDetails is not None:
            update_fields["statblockDetails"] = updates.statblockDetails

        update_fields["updatedAt"] = datetime.utcnow().isoformat()

        new_response = existing.model_copy(update=update_fields)
        self.storage[page_id] = new_response
        return new_response

    def reset_behaviour(self) -> "FakeStatblockDB":
        self._custom_get = None
        self._custom_update = None
        return self


async def _proxy_create(self, request, user_id, fake_db: FakeStatblockDB):
    return await fake_db.create_statblock_page(request, user_id)


async def _proxy_get(self, page_id, user_id, fake_db: FakeStatblockDB):
        if getattr(fake_db, "_custom_get", None):
            return await fake_db._custom_get(page_id, user_id)
        return await fake_db.get_statblock_page(page_id, user_id)


async def _proxy_update(self, page_id, user_id, updates, fake_db: FakeStatblockDB):
        if getattr(fake_db, "_custom_update", None):
            return await fake_db._custom_update(page_id, user_id, updates)
        return await fake_db.update_statblock_page(page_id, user_id, updates)


def patch_dungeonmind_db(monkeypatch, fake_db: FakeStatblockDB):
    """Route statblock DB calls to the provided fake implementation."""

    import database.dungeonmind_objects_db as db_module  # local import to avoid cycles
    from routers import statblock_pages_router

    monkeypatch.setattr(db_module, "dungeonmind_db", fake_db, raising=False)
    monkeypatch.setattr(statblock_pages_router, "dungeonmind_db", fake_db, raising=False)

    monkeypatch.setattr(
        db_module.DungeonMindObjectsDB,
        "create_statblock_page",
        lambda self, request, user_id: _proxy_create(self, request, user_id, fake_db),
        raising=False,
    )
    monkeypatch.setattr(
        db_module.DungeonMindObjectsDB,
        "get_statblock_page",
        lambda self, page_id, user_id: _proxy_get(self, page_id, user_id, fake_db),
        raising=False,
    )
    monkeypatch.setattr(
        db_module.DungeonMindObjectsDB,
        "update_statblock_page",
        lambda self, page_id, user_id, updates: _proxy_update(self, page_id, user_id, updates, fake_db),
        raising=False,
    )

    return fake_db

