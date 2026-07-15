"""Azure AI Search backend (production vector store).

Uses a single hybrid request: a vectorised query (embeddings) plus the text
query (BM25) in one call. Azure AI Search fuses them with RRF server-side and,
where the semantic ranker is enabled, applies semantic reranking. Metadata
(source/locator/classification) is returned for citation grounding.
"""
from __future__ import annotations

from typing import Any

from app.clients.embedding_client import EmbeddingClient
from app.clients.vector_store import VectorStore
from app.config import Settings
from app.core.logging import get_logger
from app.models.schemas import RetrievedChunk

logger = get_logger(__name__)


class AzureSearchVectorStore(VectorStore):
    def __init__(self, settings: Settings) -> None:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        self.settings = settings
        self.embedder = EmbeddingClient(settings)
        self._client = SearchClient(
            endpoint=settings.search_endpoint,
            index_name=settings.search_index,
            credential=AzureKeyCredential(settings.search_api_key),
        )

    def hybrid_search(
        self,
        query: str,
        top_k: int,
        scope: dict[str, str] | None = None,
    ) -> list[RetrievedChunk]:  # pragma: no cover
        from azure.search.documents.models import VectorizedQuery

        qv = self.embedder.embed_one(query)
        vq = VectorizedQuery(vector=qv, k_nearest_neighbors=top_k, fields="content_vector")
        results = self._client.search(
            search_text=query,                # BM25 leg
            vector_queries=[vq],              # vector leg (server-side RRF)
            query_type="semantic",            # semantic ranker when configured
            semantic_configuration_name="tom-semantic",
            filter=_scope_filter(scope or {}),
            top=top_k,
            select=["content", "source", "locator", "classification", "sector", "function", "technology"],
        )
        out: list[RetrievedChunk] = []
        for r in results:
            out.append(
                RetrievedChunk(
                    text=r["content"],
                    source=r.get("source", "unknown"),
                    locator=r.get("locator"),
                    classification=r.get("classification", "KPMG Confidential"),
                    sector=r.get("sector"),
                    function=r.get("function"),
                    technology=r.get("technology"),
                    score=float(r.get("@search.reranker_score", r.get("@search.score", 0.0))),
                )
            )
        return out

    def upsert(self, chunks: list[dict[str, Any]]) -> int:  # pragma: no cover
        docs = []
        for c in chunks:
            docs.append(
                {
                    "id": c["id"],
                    "content": c["text"],
                    "content_vector": self.embedder.embed_one(c["text"]),
                    "source": c.get("source", "unknown"),
                    "locator": c.get("locator"),
                    "classification": c.get("classification", "KPMG Confidential"),
                    "sector": c.get("sector", ""),
                    "function": c.get("function", ""),
                    "technology": c.get("technology", ""),
                    "content_hash": c.get("content_hash", c["id"]),
                }
            )
        self._client.upload_documents(docs)
        return len(docs)


def _scope_filter(scope: dict[str, str]) -> str | None:
    parts = []
    for key in ("sector", "function", "technology"):
        value = scope.get(key)
        if value:
            escaped = value.replace("'", "''")
            parts.append(f"{key} eq '{escaped}'")
    return " and ".join(parts) if parts else None
