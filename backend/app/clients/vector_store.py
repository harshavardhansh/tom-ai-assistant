"""Vector knowledge layer (Brain 2).

`VectorStore.hybrid_search` returns the RRF-merged top-K of a vector search and a
keyword (BM25) search — mirroring the POC's Azure AI Search hybrid flow. The
local backend implements this with numpy + a compact BM25 so the retriever runs
offline; the Azure backend delegates to Azure AI Search.
"""
from __future__ import annotations

import json
import math
import re
from abc import ABC, abstractmethod
from collections import Counter
from pathlib import Path
from typing import Optional

from app.clients.embedding_client import EmbeddingClient
from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import find_sample_data
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)
_TOKEN = re.compile(r"[a-z0-9]+")
_SAMPLE = find_sample_data("finance_vectors.json")


def _tok(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


def rrf_merge(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion over several ranked lists of doc indices."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


class VectorStore(ABC):
    @abstractmethod
    def hybrid_search(
        self,
        query: str,
        top_k: int,
        scope: dict[str, str] | None = None,
    ) -> list[RetrievedChunk]: ...

    def upsert(self, chunks: list[dict]) -> int:  # pragma: no cover
        raise NotImplementedError


class LocalVectorStore(VectorStore):
    def __init__(self, data_path: Optional[Path] = None, embedder: Optional[EmbeddingClient] = None):
        self.embedder = embedder or EmbeddingClient()
        self.docs: list[dict] = []
        self.vectors: list[list[float]] = []
        self._doc_tokens: list[list[str]] = []
        self._df: Counter = Counter()
        self._avg_len = 0.0
        path = data_path or _SAMPLE
        if path and path.exists():
            self._load(json.loads(path.read_text(encoding="utf-8-sig")))
        else:
            logger.warning("Sample vectors not found (looked for finance_vectors.json under pipeline/sample_data); vector store is empty")

    def _load(self, docs: list[dict]) -> None:
        self.docs = docs
        self.vectors = self.embedder.embed([d["text"] for d in docs]) if docs else []
        self._doc_tokens = [_tok(d["text"]) for d in docs]
        for toks in self._doc_tokens:
            self._df.update(set(toks))
        self._avg_len = (sum(len(t) for t in self._doc_tokens) / len(self._doc_tokens)) if self._doc_tokens else 0.0

    def _bm25_rank(self, query: str, k1: float = 1.5, b: float = 0.75) -> list[int]:
        q_terms = _tok(query)
        n = len(self.docs)
        scores = [0.0] * n
        for i, toks in enumerate(self._doc_tokens):
            tf = Counter(toks)
            dl = len(toks) or 1
            for term in q_terms:
                if term not in tf:
                    continue
                idf = math.log(1 + (n - self._df[term] + 0.5) / (self._df[term] + 0.5))
                denom = tf[term] + k1 * (1 - b + b * dl / (self._avg_len or 1))
                scores[i] += idf * (tf[term] * (k1 + 1)) / denom
        return sorted(range(n), key=lambda i: scores[i], reverse=True)

    def _vector_rank(self, query: str) -> list[int]:
        if not self.vectors:
            return []
        qv = self.embedder.embed_one(query)
        sims = [_cosine(qv, v) for v in self.vectors]
        return sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)

    @staticmethod
    def _matches_scope(doc: dict, scope: dict[str, str] | None) -> bool:
        if not scope:
            return True
        for key, value in scope.items():
            if value and str(doc.get(key, "")).lower() != value.lower():
                return False
        return True

    def hybrid_search(
        self,
        query: str,
        top_k: int,
        scope: dict[str, str] | None = None,
    ) -> list[RetrievedChunk]:
        if not self.docs:
            return []
        allowed = [i for i, d in enumerate(self.docs) if self._matches_scope(d, scope)]
        if not allowed:
            return []
        vector_ranking = self._vector_rank(query)[: max(top_k * 4, 20)]
        bm25_ranking = self._bm25_rank(query)[: max(top_k * 4, 20)]
        vector_ranking = [i for i in vector_ranking if i in allowed]
        bm25_ranking = [i for i in bm25_ranking if i in allowed]
        merged = rrf_merge([vector_ranking, bm25_ranking])
        out: list[RetrievedChunk] = []
        for idx, score in merged[:top_k]:
            d = self.docs[idx]
            out.append(
                RetrievedChunk(
                    text=d["text"],
                    source=d.get("source", "unknown"),
                    locator=d.get("locator"),
                    classification=d.get("classification", "KPMG Confidential"),
                    sector=d.get("sector"),
                    function=d.get("function"),
                    technology=d.get("technology"),
                    score=score,
                )
            )
        return out

    def upsert(self, chunks: list[dict]) -> int:
        by_id = {d.get("id"): d for d in self.docs if d.get("id")}
        for chunk in chunks:
            by_id[chunk.get("id")] = chunk
        self._load(list(by_id.values()))
        return len(chunks)


def get_vector_store(settings: Optional[Settings] = None) -> VectorStore:
    settings = settings or get_settings()
    if settings.vector_backend == "azure_search":
        from app.clients.vector_azure_search import AzureSearchVectorStore

        return AzureSearchVectorStore(settings)
    return LocalVectorStore()
