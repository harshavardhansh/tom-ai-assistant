"""Embedding client.

Production: Workbench `text-embedding-ada-002` (1536-dim) via the OpenAI-compatible
gateway. Offline/dev: a deterministic hash-based pseudo-embedding so the vector
pipeline runs without network access. The fallback is NOT semantically meaningful
and is gated to non-prod use only.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Optional

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_TOKEN = re.compile(r"[a-z0-9]+")


class EmbeddingClient:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.dim = self.settings.embedding_dim
        self._client = None
        if self.settings.workbench_configured:
            try:
                from openai import OpenAI

                self._client = OpenAI(
                    base_url=self.settings.workbench_openai_base_url,
                    api_key=self.settings.workbench_openai_api_key,
                    default_query={"api-version": self.settings.workbench_api_version},
                )
            except Exception as exc:  # pragma: no cover
                logger.warning("Embedding client init failed; using local stub: %s", exc)

    @property
    def available(self) -> bool:
        return self._client is not None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.available:
            resp = self._client.embeddings.create(  # type: ignore[union-attr]
                model=self.settings.embedding_deployment, input=texts
            )
            return [d.embedding for d in resp.data]
        return [self._local_embed(t) for t in texts]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _local_embed(self, text: str) -> list[float]:
        """Hashing vectorizer: stable, L2-normalised, dev-only."""
        vec = [0.0] * self.dim
        for tok in _TOKEN.findall(text.lower()):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]
