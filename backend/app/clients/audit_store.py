"""Durable conversation audit store.

Redis keeps the short rolling prompt window; Cosmos DB stores who asked what,
which answer was returned, and when. The app degrades to a no-op audit store only
in local dev/test when Cosmos is intentionally absent.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from app.config import Settings, get_settings


class AuditStore:
    def record_exchange(
        self, session_id: str, question: str, answer: str, citations: Optional[list] = None
    ) -> None:
        raise NotImplementedError


class NullAuditStore(AuditStore):
    def record_exchange(
        self, session_id: str, question: str, answer: str, citations: Optional[list] = None
    ) -> None:
        return None


class CosmosAuditStore(AuditStore):  # pragma: no cover - requires Azure Cosmos
    def __init__(self, settings: Settings) -> None:
        from azure.cosmos import CosmosClient, PartitionKey

        client = CosmosClient(settings.cosmos_memory_endpoint, credential=settings.cosmos_memory_key)
        db = client.create_database_if_not_exists(settings.cosmos_memory_database)
        self._container = db.create_container_if_not_exists(
            id=settings.cosmos_memory_container,
            partition_key=PartitionKey(path="/session_id"),
        )

    def record_exchange(
        self, session_id: str, question: str, answer: str, citations: Optional[list] = None
    ) -> None:
        self._container.upsert_item(
            {
                "id": str(uuid4()),
                "session_id": session_id,
                "question": question,
                "answer": answer,
                # Which sources grounded the answer (OWASP LLM08: immutable
                # retrieval lineage per exchange).
                "citations": [
                    {
                        "source": getattr(c, "source", None),
                        "locator": getattr(c, "locator", None),
                        "classification": getattr(c, "classification", None),
                    }
                    for c in (citations or [])
                ],
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "record_type": "qa_exchange",
            }
        )


def get_audit_store(settings: Optional[Settings] = None) -> AuditStore:
    settings = settings or get_settings()
    if settings.cosmos_memory_endpoint and settings.cosmos_memory_key:
        return CosmosAuditStore(settings)
    return NullAuditStore()
