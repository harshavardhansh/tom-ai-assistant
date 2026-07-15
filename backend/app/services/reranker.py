"""Reranking + relevance-threshold filtering (POC: +40% quality; threshold
prevents hallucinations).

Production uses a cross-encoder / Azure AI Search semantic ranker. The local
reranker scores (query, passage) relevance by blending embedding cosine with
lexical overlap, then drops passages below the configured threshold. If nothing
clears the bar, the caller returns an honest "insufficient grounding" answer
instead of fabricating one.
"""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from typing import Optional

from app.clients.embedding_client import EmbeddingClient
from app.config import get_settings
from app.models.schemas import RetrievedChunk

_TOKEN = re.compile(r"[a-z0-9]+")


def _overlap(query: str, text: str) -> float:
    q = set(_TOKEN.findall(query.lower()))
    d = set(_TOKEN.findall(text.lower()))
    if not q:
        return 0.0
    return len(q & d) / len(q)


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class Reranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]: ...


class LocalReranker(Reranker):
    def __init__(self, embedder: Optional[EmbeddingClient] = None, threshold: Optional[float] = None):
        self.embedder = embedder or EmbeddingClient()
        self.threshold = get_settings().rerank_relevance_threshold if threshold is None else threshold

    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        if not chunks:
            return []
        qv = self.embedder.embed_one(query)
        doc_vecs = self.embedder.embed([c.text for c in chunks])
        for chunk, dv in zip(chunks, doc_vecs):
            sem = (_cosine(qv, dv) + 1) / 2  # map [-1,1] -> [0,1]
            lex = _overlap(query, chunk.text)
            chunk.score = round(0.7 * sem + 0.3 * lex, 4)
        kept = [c for c in chunks if c.score >= self.threshold]
        kept.sort(key=lambda c: c.score, reverse=True)
        return kept
