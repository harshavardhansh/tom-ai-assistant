"""Graph Navigator (Brain 1 facade).

Wraps the graph store + synthesis into a single call the orchestrator can use,
returning a narrative, optional process-flow JSON (for the visualizer), and the
raw rows used (for grounded follow-up suggestions).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.clients.graph_store import GraphStore, get_graph_store
from app.core.logging import get_logger
from app.models.schemas import GraphResult
from app.services.synthesis import Synthesizer

logger = get_logger(__name__)


@dataclass
class GraphAnswer:
    narrative: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    process_flow: Optional[dict[str, Any]] = None
    query: str = ""


class GraphNavigator:
    def __init__(self, store: Optional[GraphStore] = None, synth: Optional[Synthesizer] = None):
        self.store = store or get_graph_store()
        self.synth = synth or Synthesizer()

    def answer(
        self,
        question: str,
        history: str = "(no prior turns)",
        scope: dict[str, str] | None = None,
        persona: str | None = None,
    ) -> GraphAnswer:
        result: GraphResult = self.store.natural_language_query(question, scope or {})
        narrative = self.synth.graph_answer(question, result, history, persona)
        return GraphAnswer(
            narrative=narrative,
            rows=result.rows,
            process_flow=result.process_flow,
            query=result.query,
        )
