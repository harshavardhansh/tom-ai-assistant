"""Application configuration.

Precedence: environment variables / .env  ->  Azure Key Vault  ->  defaults.
No secret is ever hard-coded. In production all secrets resolve from Key Vault
via managed identity; in local dev they come from a gitignored .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- App ----
    app_name: str = "TOM AI Knowledge Assistant"
    environment: Literal["dev", "test", "uat", "prod"] = "dev"
    log_level: str = "INFO"
    document_classification: str = "KPMG Confidential"
    allowed_cors_origins: str = ""  # comma-separated SPA origins for non-dev

    # ---- Backend selection (config-only switching) ----
    graph_backend: Literal["neo4j", "gremlin", "memory"] = "memory"
    vector_backend: Literal["azure_search", "local"] = "local"
    cache_backend: Literal["redis", "memory"] = "memory"

    # ---- KPMG Workbench OpenAI (API-key access) ----
    # Workbench exposes OpenAI-compatible chat + embedding deployments.
    workbench_openai_base_url: str = ""
    workbench_openai_api_key: str = ""
    workbench_api_version: str = "2024-06-01"
    chat_deployment: str = "gpt-4"
    embedding_deployment: str = "text-embedding-ada-002"
    embedding_dim: int = 1536
    llm_temperature: float = 0.1
    llm_max_tokens: int = 1500

    # ---- Neo4j (dev / prototype) ----
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # ---- Cosmos DB for Gremlin (production graph) ----
    gremlin_endpoint: str = ""
    gremlin_database: str = "tom"
    gremlin_graph: str = "processes"
    gremlin_key: str = ""

    # ---- Azure AI Search (production vector) ----
    search_endpoint: str = ""
    search_index: str = "tom-knowledge"
    search_api_key: str = ""

    # ---- Redis / Cosmos memory ----
    redis_url: str = ""
    cosmos_memory_endpoint: str = ""
    cosmos_memory_key: str = ""
    cosmos_memory_database: str = "tom"
    cosmos_memory_container: str = "conversation_audit"

    # ---- Retrieval tuning ----
    hybrid_top_k: int = 5
    rerank_relevance_threshold: float = 0.35  # below this -> dropped (anti-hallucination)
    memory_window: int = 5  # last N Q&A pairs (per POC)

    # ---- Auth (Entra ID) ----
    auth_disabled: bool = True  # dev convenience; MUST be False in uat/prod
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_api_audience: str = ""

    # ---- Key Vault ----
    key_vault_uri: str = ""

    # ---- Ingestion control plane ----
    ingestion_raw_dir: str = "pipeline/raw"
    ingestion_processed_dir: str = "pipeline/processed"
    defender_scan_endpoint: str = ""

    # ---- Concurrency ----
    multihop_branch_timeout_s: float = 25.0

    @property
    def workbench_configured(self) -> bool:
        return bool(self.workbench_openai_base_url and self.workbench_openai_api_key)

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_cors_origins.split(",") if o.strip()]

    def validate_runtime(self) -> None:
        """Fail closed when a shared environment is missing enterprise controls."""
        if self.environment in {"uat", "prod"}:
            missing: list[str] = []
            if self.auth_disabled:
                missing.append("AUTH_DISABLED=false")
            for name in ("entra_tenant_id", "entra_client_id", "entra_api_audience"):
                if not getattr(self, name):
                    missing.append(name.upper())
            if not self.workbench_configured:
                missing.append("WORKBENCH_OPENAI_BASE_URL/WORKBENCH_OPENAI_API_KEY")
            if self.graph_backend != "gremlin":
                missing.append("GRAPH_BACKEND=gremlin")
            if self.vector_backend != "azure_search":
                missing.append("VECTOR_BACKEND=azure_search")
            if self.cache_backend != "redis":
                missing.append("CACHE_BACKEND=redis")
            for name in (
                "key_vault_uri",
                "gremlin_endpoint",
                "search_endpoint",
                "redis_url",
                "cosmos_memory_endpoint",
                "cosmos_memory_key",
            ):
                if not getattr(self, name):
                    missing.append(name.upper())
            if not self.defender_scan_endpoint:
                missing.append("DEFENDER_SCAN_ENDPOINT")
            if not self.cors_origins:
                missing.append("ALLOWED_CORS_ORIGINS")
            if missing:
                raise RuntimeError(
                    "Unsafe UAT/prod configuration. Missing or invalid: "
                    + ", ".join(sorted(set(missing)))
                )


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Pull secrets from Key Vault when a URI is configured and a value is blank.
    if s.key_vault_uri:
        try:
            from app.clients.keyvault import hydrate_from_key_vault

            hydrate_from_key_vault(s)
        except Exception:  # pragma: no cover - Key Vault optional in dev
            if s.environment in {"uat", "prod"}:
                raise
    s.validate_runtime()
    return s
