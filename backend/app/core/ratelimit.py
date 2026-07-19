"""Per-principal request rate limiting (OWASP LLM10 Unbounded Consumption).

Every LLM-backed endpoint costs tokens and RU/s downstream, so uncontrolled
request volume is both a denial-of-service and a denial-of-wallet risk. This
limiter applies a fixed one-minute window per authenticated principal, built on
the existing Cache abstraction: an in-process counter in dev, Redis in uat/prod
(atomic INCR), so multi-replica deployments share one budget without new
infrastructure.

`RATE_LIMIT_PER_MINUTE=0` disables the limiter (e.g. for load testing).
The Application Gateway WAF in front of the app provides coarse network-level
protection; this adds the per-identity budget OWASP recommends.
"""
from __future__ import annotations

import time
from functools import lru_cache

from fastapi import Depends, HTTPException, status

from app.clients.cache import Cache, get_cache
from app.config import get_settings
from app.core.logging import get_logger
from app.core.security import Principal, get_principal

logger = get_logger(__name__)
_WINDOW_S = 60


@lru_cache
def _limiter_cache() -> Cache:
    # One shared instance so in-process counters survive across requests.
    return get_cache()


def check_rate_limit(principal_oid: str, limit: int | None = None) -> None:
    """Raise 429 when `principal_oid` exceeds its per-minute request budget."""
    if limit is None:
        limit = get_settings().rate_limit_per_minute
    if limit <= 0:  # disabled
        return
    window = int(time.time() // _WINDOW_S)
    key = f"tom:rl:{principal_oid}:{window}"
    count = _limiter_cache().incr(key, ttl_s=_WINDOW_S * 2)
    if count > limit:
        retry_after = _WINDOW_S - int(time.time() % _WINDOW_S)
        logger.info("Rate limit exceeded for principal %s (%d/%d)", principal_oid, count, limit)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded. Please retry shortly.",
            headers={"Retry-After": str(retry_after)},
        )


async def rate_limited_principal(
    principal: Principal = Depends(get_principal),
) -> Principal:
    """FastAPI dependency: authenticate, then enforce the per-principal budget."""
    check_rate_limit(principal.oid)
    return principal
