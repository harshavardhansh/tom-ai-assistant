"""Answer synthesis.

When the Workbench LLM is available, synthesis uses GPT-4-class grounded prompts.
Offline, deterministic formatters produce clean, faithful answers from the same
structured inputs — so the assistant never fabricates and always returns
something useful in dev.
"""
from __future__ import annotations

from typing import Any

from app.clients.llm_client import LLMClient
from app.core.logging import get_logger
from app.models.schemas import BranchResult, Citation, GraphResult, RetrievedChunk
from app.prompts import templates as P

logger = get_logger(__name__)


class Synthesizer:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    # -- GRAPH ----------------------------------------------------------
    def graph_answer(
        self, question: str, result: GraphResult, history: str, persona: str | None = None
    ) -> str:
        if not result.rows:
            return ("I couldn't find that in the TOM knowledge base. Try naming a "
                    "specific process or level (for example, \"List L2 processes under Finance\").")
        if self.llm.available:
            return self.llm.chat(
                f"{P.GRAPH_SYNTHESIS_SYSTEM}\n\n{P.persona_instruction(persona)}",
                P.GRAPH_SYNTHESIS_USER.format(
                    question=question, history=history, results=_compact(result.rows)
                ),
            )
        return self._graph_fallback(result)

    def _graph_fallback(self, result: GraphResult) -> str:
        rows = result.rows
        if result.query == "count":
            r = rows[0]
            return f"There are **{r['count']}** L{r['level']} processes."
        if result.query in {"list_level", "children"}:
            lead = f"Found {len(rows)} process(es):"
            bullets = "\n".join(f"- {r['name']} (`{r['code']}`, L{r.get('level','?')})" for r in rows)
            return f"{lead}\n{bullets}"
        if result.query == "roles":
            return "Roles involved:\n" + "\n".join(f"- {r['role']}" for r in rows)
        if result.query == "controls":
            return "Controls:\n" + "\n".join(f"- {r['control']}" for r in rows)
        if result.query == "process_flow" and result.process_flow:
            steps = result.process_flow.get("steps", [])
            return (f"Process flow for **{result.process_flow.get('name','process')}** "
                    f"({len(steps)} steps) — see the diagram below.")
        return "\n".join(f"- {r}" for r in rows)

    # -- VECTOR ---------------------------------------------------------
    def vector_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        history: str,
        persona: str | None = None,
    ) -> tuple[str, list[Citation]]:
        if not chunks:
            return (
                "I don't have grounded information on that in the current TOM document set, "
                "so I won't guess. You can rephrase, or upload the relevant TOM material.",
                [],
            )
        citations = [
            Citation(
                label=str(i + 1),
                source=c.source,
                locator=c.locator,
                classification=c.classification,
                sector=c.sector,
                function=c.function,
                technology=c.technology,
            )
            for i, c in enumerate(chunks)
        ]
        if self.llm.available:
            context = "\n\n".join(f"[{i+1}] ({c.source}) {c.text}" for i, c in enumerate(chunks))
            answer = self.llm.chat(
                f"{P.VECTOR_SYNTHESIS_SYSTEM}\n\n{P.persona_instruction(persona)}",
                P.VECTOR_SYNTHESIS_USER.format(question=question, history=history, context=context),
            )
            return answer, citations
        return self._vector_fallback(chunks), citations

    def _vector_fallback(self, chunks: list[RetrievedChunk]) -> str:
        lead = "Based on the most relevant TOM documents:"
        body = "\n\n".join(f"{c.text} [{i+1}]" for i, c in enumerate(chunks[:3]))
        return f"{lead}\n\n{body}"

    # -- MULTIHOP -------------------------------------------------------
    def unified_answer(
        self,
        question: str,
        branches: list[BranchResult],
        history: str,
        persona: str | None = None,
    ) -> tuple[str, list[Citation]]:
        # Merge & renumber citations across branches.
        merged: list[Citation] = []
        for b in branches:
            merged.extend(b.citations)
        for i, c in enumerate(merged, 1):
            c.label = str(i)
        if self.llm.available:
            rendered = "\n\n".join(f"[{b.route.value}] {b.sub_question}\n{b.narrative}" for b in branches)
            answer = self.llm.chat(
                f"{P.UNIFIED_SYNTHESIS_SYSTEM}\n\n{P.persona_instruction(persona)}",
                P.UNIFIED_SYNTHESIS_USER.format(question=question, history=history, branches=rendered),
            )
            return answer, merged
        parts = [f"**{b.sub_question.rstrip('?')}.**\n{b.narrative}" for b in branches]
        return "\n\n".join(parts), merged


def _compact(rows: list[dict[str, Any]], limit: int = 50) -> str:
    import json

    return json.dumps(rows[:limit], ensure_ascii=False)
