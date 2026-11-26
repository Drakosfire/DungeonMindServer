import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from generationengine import GenerationClient
from generationengine.providers.openai_text import OpenAITextProvider
from ruleslawyer.ruleslawyer_helper import generate_bot_response_stream


@pytest.mark.asyncio
async def test_luna_wire_request_and_streamed_citations():
    captured = {}
    deltas = ["What is the target's AC? [", "E1]", " [E99]"]

    @asynccontextmanager
    async def open_stream(**kwargs):
        captured.update(kwargs)

        async def events():
            for delta in deltas:
                yield SimpleNamespace(type="response.output_text.delta", delta=delta)
            yield SimpleNamespace(type="response.completed")
        yield events()

    client = GenerationClient(text_provider=OpenAITextProvider(
        client=SimpleNamespace(responses=SimpleNamespace(stream=open_stream))
    ))

    class Evidence:
        def retrieve_relevant_resources(self, question, limit):
            assert question == "Can my missed attack still deal Shock?"
            assert limit == 20
            return [{"chunk": {"id": "a" * 64, "source_sha256": "host-source-hash",
                               "printed_page": 43, "pdf_page": 46, "section": "Shock",
                               "content": "Shock can depend on a target's Armor Class."}}]

    stream, history = await generate_bot_response_stream(
        "Can my missed attack still deal Shock?", [], Evidence(), client, rulebook_id="WWN_Free_Edition"
    )
    events = [frame async for frame in stream]
    assert captured["model"] == "gpt-6-luna"
    assert captured["reasoning"] == {"effort": "low"}
    assert "temperature" not in captured
    assert all(token not in str(captured) for token in ("a" * 64, "host-source-hash", "WWN_Free_Edition"))
    assert "[E1]" in str(captured) and "missing fact" in str(captured)
    body = "".join(events)
    assert "[p. 43]" in body and "[E99]" not in body and "Citations: p. 43" in body
    complete = next(json.loads(frame[6:]) for frame in events if '"stage": "complete"' in frame)
    assert complete["metadata"]["citations"] == [{
        "page": 43, "pdfPage": 46, "sourceId": "a" * 64,
        "link": "/api/ruleslawyer/evidence/WWN_Free_Edition/" + "a" * 64,
        "sourceHash": "host-source-hash", "section": "Shock",
    }]
    assert events[-1] == "data: [DONE]\n\n"
    assert len(history) == 1


@pytest.mark.asyncio
async def test_source_open_is_bound_to_book_and_exact_unit(monkeypatch, tmp_path):
    from fastapi import HTTPException
    from routers import ruleslawyer_router as routes

    unit = "a" * 64
    (tmp_path / "manifest.json").touch()
    monkeypatch.setattr(routes, "RULESLAWYER_DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "RulesIndexManifest", lambda root: SimpleNamespace(books={
        "WWN_Free_Edition": {"title": "WWN", "source_sha256": "expected"},
    }))
    loader = SimpleNamespace(indices_by_id={unit: 0}, pages_and_chunks=[{
        "source_sha256": "expected", "printed_page": 43, "pdf_page": 46,
        "content": "<script>unsafe</script>", "section": "Shock",
    }])
    monkeypatch.setattr(routes.rules_lawyer_service, "get_loader", lambda book: loader)
    response = await routes.open_evidence("WWN_Free_Edition", unit)
    assert "Printed page 43 · PDF page 46" in response.body.decode()
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in response.body.decode()
    with pytest.raises(HTTPException) as caught:
        await routes.open_evidence("Other_book", unit)
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_legacy_rows_cite_exact_passages_without_serialized_headings(monkeypatch, tmp_path):
    import numpy as np
    from routers import ruleslawyer_router as routes
    from ruleslawyer import ruleslawyer_helper as helper

    book = "DnD_PHB_55"
    source = "b" * 64
    chunks = [
        {"page": 215, "sections": "[]", "content": "| Club | 1d4 |"},
        {"page": 215, "sections": '["Equipment", "Weapons"]', "content": "| Dagger | 1d4 |"},
    ]
    monkeypatch.setattr(helper, "load_encoder", lambda: SimpleNamespace(encode=lambda _: np.ones(768)))
    loader = helper.EmbeddingLoader(cached_data=(chunks, np.ones((2, 768))), legacy_evidence_hash=source)
    assert chunks[0]["id"] != chunks[1]["id"]
    citations = helper.CitationOutput(chunks, book)
    assert citations.feed("[E1][E2]", final=True) == "[p. 215][p. 215]"
    assert citations.used["[E1]"]["section"] is None
    assert citations.used["[E2]"]["section"] == "Equipment / Weapons"

    (tmp_path / "manifest.json").touch()
    monkeypatch.setattr(routes, "RULESLAWYER_DATA_DIR", tmp_path)
    monkeypatch.setattr(routes, "RulesIndexManifest", lambda root: SimpleNamespace(books={
        book: {"title": "PHB 2024", "source_index_sha256": source},
    }))
    monkeypatch.setattr(routes.rules_lawyer_service, "get_loader", lambda book: loader)
    for label, chunk in zip(("[E1]", "[E2]"), chunks, strict=True):
        assert citations.used[label]["link"].endswith(chunk["id"])
        response = await routes.open_evidence(book, chunk["id"])
        assert chunk["content"] in response.body.decode()
        assert "Printed page 215" in response.body.decode()
        assert "<h2>[]</h2>" not in response.body.decode()
