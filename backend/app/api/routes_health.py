"""Health & readiness endpoints. Readiness reports which backends are wired so
operators can see at a glance whether the app is in offline-dev mode or fully
connected to Azure services."""
from __future__ import annotations

from fastapi import APIRouter

from app.clients.embedding_client import EmbeddingClient
from app.clients.llm_client import LLMClient
from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ready",
        "environment": settings.environment,
        "backends": {
            "graph": settings.graph_backend,
            "vector": settings.vector_backend,
            "cache": settings.cache_backend,
        },
        "llm_available": LLMClient().available,
        "embeddings_available": EmbeddingClient().available,
        "auth_disabled": settings.auth_disabled,
    }
