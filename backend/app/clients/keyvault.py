"""Hydrate blank secret fields from Azure Key Vault using managed identity.

Secret naming convention in the vault (kebab-case of the setting):
  workbench-openai-api-key, neo4j-password, gremlin-key, search-api-key,
  cosmos-memory-key, redis-url, ...
Only fields that are currently blank are overwritten, so explicit env values win.
"""
from __future__ import annotations

from app.core.logging import get_logger

logger = get_logger(__name__)

# setting attribute -> Key Vault secret name
_SECRET_MAP = {
    "workbench_openai_api_key": "workbench-openai-api-key",
    "neo4j_password": "neo4j-password",
    "gremlin_key": "gremlin-key",
    "search_api_key": "search-api-key",
    "cosmos_memory_key": "cosmos-memory-key",
    "redis_url": "redis-url",
}


def hydrate_from_key_vault(settings) -> None:  # pragma: no cover - needs Azure
    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(
        vault_url=settings.key_vault_uri, credential=DefaultAzureCredential()
    )
    for attr, secret_name in _SECRET_MAP.items():
        if getattr(settings, attr, ""):
            continue  # explicit value already provided
        try:
            value = client.get_secret(secret_name).value
            if value:
                setattr(settings, attr, value)
        except Exception as exc:
            logger.debug("Key Vault secret %s not loaded: %s", secret_name, exc)
