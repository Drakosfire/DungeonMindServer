import csv
import json

import numpy as np
import pytest

from ruleslawyer import ruleslawyer_helper
from ruleslawyer.index_manifest import RulesIndexManifest, fingerprint
from ruleslawyer.mpnet import MAX_TOKENS, MODEL_ID, MODEL_REVISION, VECTOR_DIMENSION


def test_manifest_rejects_swapped_or_modified_book(tmp_path):
    book = "WWN_Free_Edition"
    index = tmp_path / f"{book}_embeddings.csv"
    metadata = tmp_path / f"{book}.json"
    index.write_text("original vectors")
    metadata.write_text("{}")
    (tmp_path / "manifest.json").write_text(json.dumps({
        "model": MODEL_ID, "revision": MODEL_REVISION, "dimension": VECTOR_DIMENSION,
        "max_tokens": MAX_TOKENS, "pooling": "attention_mask_mean",
        "normalization": "l2", "forward_dtype": "bfloat16", "vector_dtype": "float32",
        "books": {book: {"mpnet_index_sha256": fingerprint(index),
                         "metadata_sha256": fingerprint(metadata)}},
    }))
    manifest = RulesIndexManifest(tmp_path)
    manifest.verify(book, index, metadata)
    with pytest.raises(ValueError, match="filenames"):
        manifest.verify(book, metadata, index)
    index.write_text("wrong vectors")
    with pytest.raises(ValueError, match="checksum"):
        manifest.verify(book, index, metadata)


def test_loader_rejects_bge_shape_before_loading_model(monkeypatch):
    def unexpected():
        pytest.fail("Incompatible vectors must be rejected before loading weights")
    monkeypatch.setattr(ruleslawyer_helper, "load_encoder", unexpected)
    with pytest.raises(ValueError, match="768 dimensions"):
        ruleslawyer_helper.EmbeddingLoader(cached_data=([{"content": "rule"}], np.ones((1, 1024))))


def test_table_promotes_linked_rule_with_source_identity(monkeypatch, tmp_path):
    class FakeEncoder:
        def encode(self, _):
            return np.ones(768, dtype=np.float32)
    monkeypatch.setattr(ruleslawyer_helper, "load_encoder", FakeEncoder)
    fields = ("id", "content", "printed_page", "pdf_page", "source_sha256", "unit_type", "related", "embedding")
    table = {"id": "table", "unit_type": "table", "related": '["rule"]',
             "content": "<table><tr><th>Spear, Light</th><td>2</td></tr></table>"}
    rule = {"id": "rule", "unit_type": "prose", "related": "[]", "content": "Shock"}
    index = tmp_path / "index.csv"
    with index.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in (table, rule):
            writer.writerow({**row, "printed_page": 37, "pdf_page": 40,
                             "source_sha256": "test-hash", "embedding": json.dumps([1.0] * 768)})
    loader = ruleslawyer_helper.EmbeddingLoader(str(index))
    chunks = [r["chunk"] for r in loader.retrieve_relevant_resources("Can my light spear cause Shock?", 2)]
    assert [chunk["id"] for chunk in chunks] == ["table", "rule"]
    assert chunks[0]["content"] == table["content"]
    assert (chunks[0]["printed_page"], chunks[0]["pdf_page"], chunks[0]["source_sha256"]) == (37, 40, "test-hash")
