import re

import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/storegenerator", "/storegenerator/"])
def test_store_editor_serves_page_and_assets(path, test_app):
    client = TestClient(test_app)
    page = client.get(path, follow_redirects=False)

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert 'id="brewRenderer"' in page.text

    assets = re.findall(r'(?:href|src)="(/static/storegenerator/[^"]+)"', page.text)
    assert "/static/storegenerator/scripts/main.js" in assets
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200, asset
        if asset.endswith(".js"):
            assert "javascript" in response.headers["content-type"]

    sample = client.get(
        "/static/root_store/Enchanted_Roots_Gear_Emporium/"
        "Enchanted_Roots_Gear_Emporium.json"
    )
    assert sample.status_code == 200
    assert sample.json()["storeData"]


def test_store_editor_keeps_store_api_authenticated(test_app):
    client = TestClient(test_app)
    response = client.get("/api/store/list-saved-stores")
    assert response.status_code == 401


def test_new_account_has_no_saved_stores(test_app, monkeypatch):
    from types import SimpleNamespace

    from routers.auth_router import get_current_user
    from routers.store_router import firestore_utils

    monkeypatch.setattr(firestore_utils, "query_collection", lambda *args: [])
    monkeypatch.setitem(
        test_app.dependency_overrides,
        get_current_user,
        lambda: SimpleNamespace(user_id="new-user"),
    )

    response = TestClient(test_app).get("/api/store/list-saved-stores")

    assert response.status_code == 200
    assert response.json() == {"stores": []}
