"""Orchestrator — the single entry point for answering a question.

Flow: route -> retrieve (graph / vector / parallel multi-hop) -> synthesize ->
visualize (if a process flow is present) -> suggest follow-ups -> persist memory.
Emits the route badge and per-stage timings (timings_ms) for observability.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from app.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import StageTimer
from app.models.schemas import BranchResult, ChatResponse, Citation, Route
from app.prompts import templates as P
from app.services.decomposition import QuestionDecomposer
from app.services.graph_navigator import GraphNavigator
from app.services.knowledge_retriever import KnowledgeRetriever
from app.services.memory import ConversationMemory
from app.services.router import QueryRouter
from app.services.suggestions import SuggestionEngine
from app.services.synthesis import Synthesizer
from app.services.visualizer import render_process_svg

logger = get_logger(__name__)


class Orchestrator:
    def __init__(
        self,
        router: Optional[QueryRouter] = None,
        graph: Optional[GraphNavigator] = None,
        retriever: Optional[KnowledgeRetriever] = None,
        decomposer: Optional[QuestionDecomposer] = None,
        synth: Optional[Synthesizer] = None,
        memory: Optional[ConversationMemory] = None,
        suggester: Optional[SuggestionEngine] = None,
    ) -> None:
        self.router = router or QueryRouter()
        self.graph = graph or GraphNavigator()
        self.retriever = retriever or KnowledgeRetriever()
        self.decomposer = decomposer or QuestionDecomposer()
        self.synth = synth or Synthesizer()
        self.memory = memory or ConversationMemory()
        self.suggester = suggester or SuggestionEngine()
        self.branch_timeout = get_settings().multihop_branch_timeout_s

    def answer(
        self,
        question: str,
        session_id: str = "default",
        scope: dict[str, str] | None = None,
        persona: str | None = None,
    ) -> ChatResponse:
        timer = StageTimer()
        history = self.memory.as_prompt_text(session_id)
        scope = scope or {}
        persona = P.resolve_persona(persona)

        with timer.stage("route"):
            decision = self.router.route(question)

        if decision.route == Route.GRAPH:
            response = self._graph_flow(question, history, decision, timer, scope, persona)
        elif decision.route == Route.VECTOR:
            response = self._vector_flow(question, history, decision, timer, scope, persona)
        else:
            response = self._multihop_flow(question, history, decision, timer, scope, persona)

        response.session_id = session_id
        response.persona = persona
        response.timings_ms = timer.timings_ms
        with timer.stage("persist"):
            self.memory.append(session_id, question, response.answer, citations=response.citations)
        return response

    # -- single-hop graph ----------------------------------------------
    def _graph_flow(self, question, history, decision, timer, scope, persona) -> ChatResponse:
        with timer.stage("graph_retrieve"):
            ga = self.graph.answer(question, history, scope, persona)
        with timer.stage("visualize"):
            svg = render_process_svg(ga.process_flow)
        with timer.stage("suggest"):
            suggestions = self.suggester.suggest(question, rows=ga.rows)
        return ChatResponse(
            answer=ga.narrative,
            route=Route.GRAPH,
            confidence=decision.confidence,
            citations=[],
            suggested_questions=suggestions,
            process_diagram_svg=svg,
            process_flow=ga.process_flow,
        )

    # -- single-hop vector ---------------------------------------------
    def _vector_flow(self, question, history, decision, timer, scope, persona) -> ChatResponse:
        with timer.stage("vector_retrieve"):
            ra = self.retriever.answer(question, history, scope, persona)
        with timer.stage("suggest"):
            suggestions = self.suggester.suggest(question, citations=ra.citations)
        return ChatResponse(
            answer=ra.narrative,
            route=Route.VECTOR,
            confidence=decision.confidence,
            citations=ra.citations,
            suggested_questions=suggestions,
        )

    # -- multi-hop ------------------------------------------------------
    def _multihop_flow(self, question, history, decision, timer, scope, persona) -> ChatResponse:
        with timer.stage("decompose"):
            subs = self.decomposer.decompose(question)

        branches: list[BranchResult] = []
        with timer.stage("parallel_branches"):
            with ThreadPoolExecutor(max_workers=min(4, len(subs) or 1)) as pool:
                futures = {pool.submit(self._run_branch, s.text, s.route, history, scope, persona): s for s in subs}
                for fut in as_completed(futures, timeout=self.branch_timeout + 5):
                    try:
                        branches.append(fut.result(timeout=self.branch_timeout))
                    except Exception as exc:  # noqa: BLE001
                        s = futures[fut]
                        logger.warning("Branch failed (%s): %s", s.text, exc)
                        branches.append(BranchResult(s.text, s.route, "(this part could not be answered)"))

        # Preserve original sub-question order
        order = {s.text: i for i, s in enumerate(subs)}
        branches.sort(key=lambda b: order.get(b.sub_question, 0))

        with timer.stage("unified_synthesis"):
            answer, citations = self.synth.unified_answer(question, branches, history, persona)

        flow = next((b.process_flow for b in branches if b.process_flow), None)
        with timer.stage("visualize"):
            svg = render_process_svg(flow)
        with timer.stage("suggest"):
            suggestions = self.suggester.suggest(question, citations=citations)

        return ChatResponse(
            answer=answer,
            route=Route.MULTIHOP,
            confidence=decision.confidence,
            citations=citations,
            suggested_questions=suggestions,
            process_diagram_svg=svg,
            process_flow=flow,
        )

    def _run_branch(
        self,
        text: str,
        route: Route,
        history: str,
        scope: dict[str, str],
        persona: str | None = None,
    ) -> BranchResult:
        if route == Route.GRAPH:
            ga = self.graph.answer(text, history, scope, persona)
            return BranchResult(text, Route.GRAPH, ga.narrative, [], ga.process_flow)
        ra = self.retriever.answer(text, history, scope, persona)
        return BranchResult(text, Route.VECTOR, ra.narrative, ra.citations, None)
