"""Chat endpoint: accepts a question, returns a routed, grounded answer."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.ratelimit import rate_limited_principal
from app.core.security import Principal
from app.models.schemas import ChatRequest, ChatResponse
from app.services.orchestrator import Orchestrator

router = APIRouter(prefix="/api/v1", tags=["chat"])
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    # Rate-limited per principal (OWASP LLM10): each call fans out to LLM +
    # graph/vector backends, so request volume is a direct cost/DoS surface.
    principal: Principal = Depends(rate_limited_principal),
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> ChatResponse:
    # Session is namespaced per principal to keep memory isolated between users.
    session = f"{principal.oid}:{req.session_id}"
    return orchestrator.answer(
        req.question, session_id=session, scope=req.scope, persona=req.persona
    )
