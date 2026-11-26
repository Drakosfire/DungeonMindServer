"""Pinned query encoder for MPNet indexes produced by RulesIngestion."""

import os
from functools import lru_cache
from threading import Lock

import torch
from transformers import AutoModel, AutoTokenizer

MODEL_ID = "sentence-transformers/all-mpnet-base-v2"
MODEL_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"
VECTOR_DIMENSION = 768
MAX_TOKENS = 384
_load_lock = Lock()


class MPNetEncoder:
    def __init__(self):
        model_path = os.environ.get("RULESLAWYER_MPNET_SNAPSHOT", MODEL_ID)
        options = {"local_files_only": True}
        if model_path == MODEL_ID:
            options["revision"] = MODEL_REVISION
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, **options)
        self.model = AutoModel.from_pretrained(
            model_path, torch_dtype=torch.bfloat16, **options
        ).eval()

    @torch.inference_mode()
    def encode(self, text):
        tokens = self.tokenizer(
            text, truncation=True, max_length=MAX_TOKENS, return_tensors="pt"
        )
        hidden = self.model(**tokens).last_hidden_state.float()
        mask = tokens["attention_mask"].unsqueeze(-1)
        pooled = (hidden * mask).sum(1) / mask.sum(1)
        return torch.nn.functional.normalize(pooled, dim=1)[0].numpy()


@lru_cache(maxsize=1)
def _load_encoder():
    return MPNetEncoder()


def load_encoder():
    with _load_lock:
        return _load_encoder()
