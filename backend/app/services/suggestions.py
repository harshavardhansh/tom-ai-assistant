"""Suggested next questions, grounded in the data actually returned (not generic).
Uses the LLM when available; otherwise derives suggestions from returned rows /
citation sources so the feature still works offline."""
from __future__ import annotations

import json
from typing import Any, Optional

from app.clients.llm_client import LLMClient
from app.core.logging import get_logger
from app.models.schemas import Citation
from app.prompts import templates as P

logger = get_logger(__name__)


class SuggestionEngine:
    def __init__(self, llm: Optional[LLMClient] = None) -> None:
        self.llm = llm or LLMClient()

    def suggest(
        self,
        question: str,
        rows: list[dict[str, Any]] | None = None,
        citations: list[Citation] | None = None,
    ) -> list[str]:
        rows = rows or []
        citations = citations or []
        if self.llm.available:
            try:
                summary = json.dumps({"rows": rows[:10], "sources": [c.source for c in citations]})
                data = self.llm.chat_json(P.SUGGEST_SYSTEM, P.SUGGEST_USER.format(question=question, data=summary))
                if isinstance(data, list):
                    return [str(s) for s in data][:4]
            except Exception as exc:  # noqa: BLE001
                logger.info("LLM suggestions failed (%s); using fallback", exc)
        return self._fallback(rows, citations)

    def _fallback(self, rows: list[dict[str, Any]], citations: list[Citation]) -> list[str]:
        out: list[str] = []
        for r in rows[:2]:
            name = r.get("name")
            if name:
                out.append(f"What are the sub-processes of {name}?")
                out.append(f"Show the process flow for {name}.")
        if citations:
            out.append(f"What else does {citations[0].source} cover?")
        return out[:4] or ["List the L1 processes under Finance.", "What is a Target Operating Model?"]
