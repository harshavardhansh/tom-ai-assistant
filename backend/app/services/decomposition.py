"""Question decomposition for multi-hop queries.

LLM splits a compound question into ordered, route-tagged sub-questions. When the
LLM is unavailable, a deterministic splitter divides on the conjunction and routes
each half by the keyword router — enough to keep multi-hop working offline.
"""
from __future__ import annotations

import re

from app.clients.llm_client import LLMClient
from app.config import get_settings
from app.core.logging import get_logger
from app.models.schemas import Route, SubQuestion
from app.prompts import templates as P
from app.services.router import QueryRouter

logger = get_logger(__name__)
_SPLIT_RE = re.compile(r"\b(?:and|also|as well as|plus|then)\b", re.IGNORECASE)


class QuestionDecomposer:
    def __init__(self, llm: LLMClient | None = None, router: QueryRouter | None = None) -> None:
        self.llm = llm or LLMClient()
        self.router = router or QueryRouter(self.llm)

    def decompose(self, question: str) -> list[SubQuestion]:
        # Branch cap (OWASP LLM10): every sub-question fans out into its own
        # LLM + retrieval calls, so an unbounded decomposition (whether LLM-
        # produced or crafted via many conjunctions) is a cost amplifier.
        cap = get_settings().max_sub_questions
        if self.llm.available:
            try:
                data = self.llm.chat_json(P.DECOMPOSE_SYSTEM, P.DECOMPOSE_USER.format(question=question))
                subs = [
                    SubQuestion(text=s["text"].strip(), route=Route(str(s["route"]).upper()))
                    for s in data.get("sub_questions", [])
                    if s.get("text")
                ]
                if subs:
                    return subs[:cap]
            except Exception as exc:  # noqa: BLE001
                logger.info("LLM decomposition failed (%s); using deterministic split", exc)
        return self._fallback_split(question)[:cap]

    def _fallback_split(self, question: str) -> list[SubQuestion]:
        parts = [p.strip(" ,.?") for p in _SPLIT_RE.split(question) if p and p.strip(" ,.?")]
        parts = [p for p in parts if len(p) > 3] or [question]
        subs: list[SubQuestion] = []
        for part in parts:
            decision = self.router.route(part)
            route = decision.route if decision.route != Route.MULTIHOP else Route.VECTOR
            subs.append(SubQuestion(text=part, route=route))
        return subs
