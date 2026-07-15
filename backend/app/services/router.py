"""Intelligent Router (Brain 3).

Layer 1 — keyword classifier: sub-millisecond, handles the obvious cases.
Layer 2 — LLM classifier: resolves ambiguity when keyword signals are weak/mixed.
Multi-hop is detected first (compound intent), per the POC flow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.clients.llm_client import LLMClient, LLMUnavailable
from app.core.logging import get_logger
from app.models.schemas import Route
from app.prompts import templates as P

logger = get_logger(__name__)

# Structured-lookup signals -> GRAPH
_GRAPH_KW = [
    r"\blist\b", r"\bhow many\b", r"\bcount\b", r"\bnumber of\b",
    r"\bl[0-4]\b", r"\bsub-?process(es)?\b", r"\bunder\b", r"\bwithin\b",
    r"\bsteps?\b", r"\bprocess flow\b", r"\brole(s)?\b", r"\bcontrol(s)?\b",
]
# Conceptual signals -> VECTOR
_VECTOR_KW = [
    r"\bwhat is\b", r"\bwhat are\b", r"\bdifference\b", r"\bexplain\b",
    r"\bwhy\b", r"\bdefine\b", r"\bleading practice", r"\bbest practice",
    r"\bdescribe\b", r"\boverview\b", r"\bcompare\b",
]
_GRAPH_RE = [re.compile(p, re.IGNORECASE) for p in _GRAPH_KW]
_VECTOR_RE = [re.compile(p, re.IGNORECASE) for p in _VECTOR_KW]
_CONJ_RE = re.compile(r"\b(and|also|as well as|plus|then)\b", re.IGNORECASE)


@dataclass
class RouteDecision:
    route: Route
    confidence: float
    method: str  # "keyword" | "llm" | "keyword+multihop"


class QueryRouter:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def route(self, question: str) -> RouteDecision:
        g = sum(1 for r in _GRAPH_RE if r.search(question))
        v = sum(1 for r in _VECTOR_RE if r.search(question))

        # Multi-hop: a conjunction joining a structured signal AND a conceptual one.
        if _CONJ_RE.search(question) and g >= 1 and v >= 1:
            return RouteDecision(Route.MULTIHOP, 0.9, "keyword+multihop")

        # Clear keyword separation -> decide directly.
        if g and not v:
            return RouteDecision(Route.GRAPH, _kw_conf(g, v), "keyword")
        if v and not g:
            return RouteDecision(Route.VECTOR, _kw_conf(v, g), "keyword")

        # Ambiguous (both/neither) -> LLM fallback when available.
        if self.llm.available:
            try:
                data = self.llm.chat_json(P.ROUTER_SYSTEM, P.ROUTER_USER.format(question=question))
                route = Route(str(data.get("route", "VECTOR")).upper())
                conf = float(data.get("confidence", 0.6))
                return RouteDecision(route, conf, "llm")
            except (LLMUnavailable, Exception) as exc:  # noqa: BLE001
                logger.info("LLM router fallback failed (%s); using heuristic", exc)

        # Heuristic tie-break without an LLM.
        if g and v:
            return RouteDecision(Route.MULTIHOP, 0.55, "keyword")
        return RouteDecision(Route.VECTOR, 0.5, "keyword")  # default to grounded docs


def _kw_conf(win: int, lose: int) -> float:
    return min(0.95, 0.6 + 0.1 * (win - lose))
