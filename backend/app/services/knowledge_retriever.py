"""Knowledge Retriever (Brain 2 facade).

Pipeline: hybrid search (vector + BM25, RRF) -> rerank + relevance-threshold
filtering -> citation-grounded synthesis. If reranking removes every passage,
the synthesizer returns an honest "insufficient grounding" answer rather than
fabricating one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.clients.vector_store import VectorStore, get_vector_store
from app.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import Citation, RetrievedChunk
from app.services.reranker import LocalReranker, Reranker
from app.services.synthesis import Synthesizer

logger = get_logger(__name__)


@dataclass
class RetrievalAnswer:
    narrative: str
    citations: list[Citation] = field(default_factory=list)
    chunks: list[RetrievedChunk] = field(default_factory=list)


class KnowledgeRetriever:
    def __init__(
        self,
        store: Optional[VectorStore] = None,
        reranker: Optional[Reranker] = None,
        synth: Optional[Synthesizer] = None,
    ) -> None:
        self.store = store or get_vector_store()
        self.reranker = reranker or LocalReranker()
        self.synth = synth or Synthesizer()
        self.top_k = get_settings().hybrid_top_k

    def answer(
        self,
        question: str,
        history: str = "(no prior turns)",
        scope: dict[str, str] | None = None,
        persona: str | None = None,
    ) -> RetrievalAnswer:
        candidates = self.store.hybrid_search(question, self.top_k, scope or {})
        reranked = self.reranker.rerank(question, candidates)
        narrative, citations = self.synth.vector_answer(question, reranked, history, persona)
        return RetrievalAnswer(narrative=narrative, citations=citations, chunks=reranked)
