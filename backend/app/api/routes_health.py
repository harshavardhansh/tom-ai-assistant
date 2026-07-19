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
    # OWASP LLM02 / API8-style hardening: probes only need the status. Backend
    # wiring and auth mode are configuration details an unauthenticated caller
    # has no need for outside local development.
    if settings.environment != "dev":
        return {"status": "ready", "environment": settings.environment}
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
