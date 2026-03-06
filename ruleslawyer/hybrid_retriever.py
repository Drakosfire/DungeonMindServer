from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Set

import numpy as np


_TOKEN_RE_BASIC = re.compile(r"[A-Za-z0-9]+")


class HybridRetriever:
    def __init__(
        self,
        pages_and_chunks: List[Dict],
        embeddings,
        encode_fn: Optional[Callable[[str], np.ndarray]] = None,
        lexical_weight: float = 0.3,
        semantic_weight: float = 0.7,
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        graph_adjacency: Optional[Dict[str, Set[str]]] = None,
        graph_seed_k: int = 12,
        graph_depth: int = 1,
        graph_boost: float = 0.05,
        graph_decay: float = 0.5,
    ):
        """Local production hybrid retriever.

        This intentionally stays service-local rather than importing Retrieval Lab,
        but it tracks the same default fusion direction: lexical BM25-style scoring
        plus dense semantic scoring, with the dense channel weighted more heavily.
        Graph expansion remains a production-only post-fusion boost.
        """
        self.pages_and_chunks = pages_and_chunks
        self.embeddings = np.array(embeddings, dtype=np.float64)
        self.encode_fn = encode_fn
        self.lexical_weight = lexical_weight
        self.semantic_weight = semantic_weight
        self.bm25_k1 = bm25_k1
        self.bm25_b = bm25_b
        self.graph_adjacency = graph_adjacency or {}
        self.graph_seed_k = graph_seed_k
        self.graph_depth = graph_depth
        self.graph_boost = graph_boost
        self.graph_decay = graph_decay

        self._corpus_tokens = [self._tokenize(str(chunk.get("content", ""))) for chunk in pages_and_chunks]
        self._doc_lengths = np.array([len(tokens) for tokens in self._corpus_tokens], dtype=np.float64)
        self._avg_doc_length = float(np.mean(self._doc_lengths)) if len(self._doc_lengths) else 0.0
        self._doc_term_freqs = [self._build_term_freq(tokens) for tokens in self._corpus_tokens]
        self._idf = self._build_idf(self._doc_term_freqs, len(self._corpus_tokens))
        self._chunk_ids = [chunk.get("id") for chunk in pages_and_chunks]
        self._chunk_id_to_index = {
            chunk_id: idx for idx, chunk_id in enumerate(self._chunk_ids) if chunk_id
        }

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return _TOKEN_RE_BASIC.findall(text.lower())

    @staticmethod
    def _l2_normalize(vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        if norm <= 0:
            return vector
        return vector / norm

    @staticmethod
    def _build_term_freq(tokens: List[str]) -> Dict[str, int]:
        term_freq: Dict[str, int] = {}
        for token in tokens:
            term_freq[token] = term_freq.get(token, 0) + 1
        return term_freq

    @staticmethod
    def _build_idf(doc_term_freqs: List[Dict[str, int]], doc_count: int) -> Dict[str, float]:
        doc_freq: Dict[str, int] = {}
        for term_freq in doc_term_freqs:
            for term in term_freq:
                doc_freq[term] = doc_freq.get(term, 0) + 1

        idf: Dict[str, float] = {}
        for term, freq in doc_freq.items():
            idf[term] = float(np.log((doc_count - freq + 0.5) / (freq + 0.5) + 1))
        return idf

    def _lexical_scores(self, query: str) -> np.ndarray:
        terms = self._tokenize(query)
        if not terms or not self.pages_and_chunks:
            return np.zeros(len(self.pages_and_chunks), dtype=np.float64)

        scores = np.zeros(len(self.pages_and_chunks), dtype=np.float64)
        avg_doc_length = self._avg_doc_length or 1.0

        for doc_index, term_freq in enumerate(self._doc_term_freqs):
            doc_length = self._doc_lengths[doc_index] or 1.0
            score = 0.0
            for term in terms:
                if term not in term_freq:
                    continue
                tf = term_freq[term]
                idf = self._idf.get(term, 0.0)
                numerator = tf * (self.bm25_k1 + 1.0)
                denominator = tf + self.bm25_k1 * (1.0 - self.bm25_b + self.bm25_b * (doc_length / avg_doc_length))
                score += idf * (numerator / denominator)
            scores[doc_index] = score

        return scores

    def _semantic_scores(self, query: str) -> np.ndarray:
        if not self.encode_fn:
            raise ValueError("encode_fn is required for semantic scoring")

        query_embedding = self._l2_normalize(np.array(self.encode_fn(query), dtype=np.float64))
        corpus_embeddings = np.vstack([self._l2_normalize(row) for row in self.embeddings])
        return corpus_embeddings @ query_embedding

    @staticmethod
    def _normalize(scores: np.ndarray) -> np.ndarray:
        if scores.size == 0:
            return scores
        max_score = np.max(scores)
        min_score = np.min(scores)
        if max_score == min_score:
            return np.zeros_like(scores)
        return (scores - min_score) / (max_score - min_score)

    def retrieve(self, query: str, top_k: int = 4) -> List[Dict]:
        lexical_scores = self._lexical_scores(query)
        semantic_scores = self._semantic_scores(query)

        lexical_norm = self._normalize(lexical_scores)
        semantic_norm = self._normalize(semantic_scores)

        combined = (lexical_norm * self.lexical_weight) + (semantic_norm * self.semantic_weight)
        final_scores = combined.copy()
        graph_boosts = np.zeros_like(final_scores)

        if self.graph_adjacency and self._chunk_id_to_index and self.graph_depth > 0:
            seed_count = min(max(top_k, self.graph_seed_k), len(final_scores))
            seed_indices = np.argsort(combined)[::-1][:seed_count]
            for seed_idx in seed_indices:
                seed_id = self._chunk_ids[int(seed_idx)]
                if not seed_id:
                    continue
                frontier = {seed_id}
                visited = {seed_id}
                for depth in range(1, self.graph_depth + 1):
                    next_frontier = set()
                    for node_id in frontier:
                        for neighbor_id in self.graph_adjacency.get(node_id, set()):
                            if neighbor_id in visited:
                                continue
                            visited.add(neighbor_id)
                            next_frontier.add(neighbor_id)
                            neighbor_index = self._chunk_id_to_index.get(neighbor_id)
                            if neighbor_index is None:
                                continue
                            graph_boosts[neighbor_index] += self.graph_boost * (self.graph_decay ** (depth - 1))
                    frontier = next_frontier

            final_scores = final_scores + graph_boosts

        ranked_indices = np.argsort(final_scores)[::-1][:top_k]

        results = []
        for index in ranked_indices:
            results.append({
                "chunk": self.pages_and_chunks[int(index)],
                "score": float(final_scores[int(index)]),
                "base_score": float(combined[int(index)]),
                "graph_boost": float(graph_boosts[int(index)]),
                "lexical_score": float(lexical_scores[int(index)]),
                "semantic_score": float(semantic_scores[int(index)]),
            })

        return results
