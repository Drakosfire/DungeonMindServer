import numpy as np

from ruleslawyer.hybrid_retriever import HybridRetriever


def test_retriever_prefers_lexical_match():
    pages_and_chunks = [
        {"content": "This section describes fireball rules and damage.", "page": 112},
        {"content": "General spellcasting overview with no specific spell names.", "page": 40},
    ]
    embeddings = np.array([
        [0.9, 0.1],
        [0.9, 0.1],
    ])

    retriever = HybridRetriever(
        pages_and_chunks=pages_and_chunks,
        embeddings=embeddings,
        encode_fn=lambda _: np.array([1.0, 0.0]),
        lexical_weight=0.6,
        semantic_weight=0.4,
    )

    results = retriever.retrieve("fireball", top_k=2)

    assert results[0]["chunk"]["page"] == 112


def test_retriever_returns_scores():
    pages_and_chunks = [
        {"content": "Attack roll rules.", "page": 12},
    ]
    embeddings = np.array([
        [0.2, 0.8],
    ])

    retriever = HybridRetriever(
        pages_and_chunks=pages_and_chunks,
        embeddings=embeddings,
        encode_fn=lambda _: np.array([0.2, 0.8]),
    )

    results = retriever.retrieve("attack roll", top_k=1)
    result = results[0]

    assert "score" in result
    assert "lexical_score" in result
    assert "semantic_score" in result
