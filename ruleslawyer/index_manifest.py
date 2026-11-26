"""Serving contract for locally packaged MPNet indexes."""

import hashlib
import json
from pathlib import Path

from ruleslawyer.mpnet import MAX_TOKENS, MODEL_ID, MODEL_REVISION, VECTOR_DIMENSION


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class RulesIndexManifest:
    def __init__(self, root: Path):
        self.root = root
        data = json.loads((root / "manifest.json").read_text())
        actual = (data["model"], data["revision"], data["dimension"], data["max_tokens"],
                  data["pooling"], data["normalization"], data["forward_dtype"], data["vector_dtype"])
        expected = (MODEL_ID, MODEL_REVISION, VECTOR_DIMENSION, MAX_TOKENS,
                    "attention_mask_mean", "l2", "bfloat16", "float32")
        if actual != expected:
            raise ValueError("Rules Lawyer artifact was built with a different embedding recipe")
        self.books = data["books"]

    def verify(self, book: str, index: Path, metadata: Path) -> None:
        entry = self.books[book]
        if index != self.root / f"{book}_embeddings.csv" or metadata != self.root / f"{book}.json":
            raise ValueError("Rules Lawyer artifact filenames do not match the selected edition")
        if fingerprint(index) != entry["mpnet_index_sha256"] or fingerprint(metadata) != entry["metadata_sha256"]:
            raise ValueError("Rules Lawyer artifact checksum mismatch")
