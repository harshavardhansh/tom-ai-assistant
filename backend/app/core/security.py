"""Authentication & authorization.

Production: validate Microsoft Entra ID access tokens (RS256) against the tenant
JWKS, check audience/issuer, and enforce app roles (RBAC). Dev: when
`AUTH_DISABLED` is true, a synthetic principal is returned so the app runs
locally without a tenant. AUTH_DISABLED must be false in uat/prod.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    oid: str
    name: str
    roles: list[str] = field(default_factory=list)


@lru_cache
def _jwks_client(tenant_id: str):  # pragma: no cover - needs network
    from jwt import PyJWKClient

    url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
    return PyJWKClient(url)


def _validate_token(token: str, settings: Settings) -> Principal:  # pragma: no cover
    import jwt

    signing_key = _jwks_client(settings.entra_tenant_id).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.entra_api_audience or settings.entra_client_id,
        issuer=f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0",
    )
    return Principal(
        oid=claims.get("oid", claims.get("sub", "unknown")),
        name=claims.get("name", claims.get("preferred_username", "user")),
        roles=claims.get("roles", []),
    )


async def get_principal(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    if settings.auth_disabled:
        return Principal(oid="dev-user", name="Local Developer", roles=["consultant"])
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return _validate_token(creds.credentials, settings)
    except Exception as exc:  # noqa: BLE001
        logger.info("Token validation failed: %s", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token") from exc


def require_role(role: str):
    async def _checker(principal: Principal = Depends(get_principal)) -> Principal:
        settings = get_settings()
        if settings.auth_disabled or role in principal.roles:
            return principal
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role '{role}'")

    return _checker
