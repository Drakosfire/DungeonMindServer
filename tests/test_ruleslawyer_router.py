import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dependencies import get_current_user
from routers import ruleslawyer_router


class FakeRegistry:
    def __init__(self):
        self.refreshed = None

    def list_rulebooks(self):
        return [
            {"id": "DnD_PHB_55", "title": "PHB 2024", "availabilityStatus": "available"},
            {"id": "swon", "title": "Stars Without Number", "availabilityStatus": "available"},
        ]

    def refresh_rulebooks(self, rulebook_ids, reason=None):
        self.refreshed = {"rulebookIds": rulebook_ids, "reason": reason}
        return {"status": "accepted", "refreshedRulebooks": rulebook_ids}


class FakeSavedRulesRepository:
    def __init__(self):
        self.saved = []

    def list_by_user(self, user_id):
        return self.saved

    def save_rule(self, user_id, payload):
        record = {
            "id": "saved-1",
            "userId": user_id,
            **payload,
        }
        self.saved.append(record)
        return record


def build_app(registry=None):
    app = FastAPI()
    app.include_router(ruleslawyer_router.router, prefix="/api/ruleslawyer")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user"}
    if registry is not None:
        app.dependency_overrides[ruleslawyer_router.get_ruleslawyer_registry] = lambda: registry
    return app


def test_query_stream_includes_citations_and_example(monkeypatch):
    async def fake_generate_bot_response_stream(*args, **kwargs):
        async def generator():
            content = (
                "Answer: The rule is X.\n\n"
                "## Example\nA short example.\n\n"
                "Citations: p.12\n\n"
                "What else can I help with?"
            )
            yield f"data: {json.dumps(content)}\n\n"
            yield "data: [DONE]\n\n"

        return generator(), []

    ruleslawyer_router.rules_lawyer_service.loader = object()
    monkeypatch.setattr(ruleslawyer_router, "generate_bot_response_stream", fake_generate_bot_response_stream)

    app = build_app()
    client = TestClient(app)

    payload = {
        "message": "How does grappling work?",
        "rulebookId": "DnD_PHB_55",
        "chatHistory": [],
    }

    with client.stream("POST", "/api/ruleslawyer/query", json=payload) as response:
        body = "".join(list(response.iter_text()))

    assert response.status_code == 200
    assert "Citations:" in body
    assert "Example" in body


def test_query_stream_includes_progress_events(monkeypatch):
    async def fake_generate_bot_response_stream(*args, **kwargs):
        async def generator():
            yield 'data: {"type":"progress","stage":"search","message":"Searching..."}\n\n'
            yield 'data: "Answer."\n\n'
            yield "data: [DONE]\n\n"

        return generator(), []

    ruleslawyer_router.rules_lawyer_service.loader = object()
    monkeypatch.setattr(ruleslawyer_router, "generate_bot_response_stream", fake_generate_bot_response_stream)

    app = build_app()
    client = TestClient(app)

    payload = {
        "message": "How does grappling work?",
        "rulebookId": "DnD_PHB_55",
        "chatHistory": [],
    }

    with client.stream("POST", "/api/ruleslawyer/query", json=payload) as response:
        body = "".join(list(response.iter_text()))

    assert response.status_code == 200
    assert '"type":"progress"' in body


def test_rulebook_list_endpoint():
    registry = FakeRegistry()
    app = build_app(registry=registry)
    client = TestClient(app)

    response = client.get("/api/ruleslawyer/rulebooks")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["rulebooks"]) == 2
    assert payload["rulebooks"][0]["id"] == "DnD_PHB_55"


def test_rulebook_refresh_endpoint():
    registry = FakeRegistry()
    app = build_app(registry=registry)
    client = TestClient(app)

    response = client.post("/api/ruleslawyer/rulebooks/refresh", json={
        "rulebookIds": ["DnD_PHB_55"],
        "reason": "unit-test"
    })

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["refreshedRulebooks"] == ["DnD_PHB_55"]


def test_saved_rules_list_and_save():
    registry = FakeRegistry()
    repo = FakeSavedRulesRepository()
    app = build_app(registry=registry)
    app.dependency_overrides[ruleslawyer_router.get_saved_rules_repo] = lambda: repo
    client = TestClient(app)

    response = client.get("/api/ruleslawyer/saved-rules")
    assert response.status_code == 200
    assert response.json() == {"rules": []}

    save_response = client.post("/api/ruleslawyer/saved-rules", json={
        "rulebookId": "DnD_PHB_55",
        "queryText": "What is advantage?",
        "responseText": "Answer with citations.",
        "citations": [{"page": 173}],
        "tags": ["combat"]
    })

    assert save_response.status_code == 200
    payload = save_response.json()
    assert payload["rulebookId"] == "DnD_PHB_55"
    assert payload["userId"] == "test-user"
