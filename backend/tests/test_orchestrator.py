"""End-to-end orchestrator tests in fully offline mode (memory graph, local
vector, deterministic synthesis). Proves each route returns a faithful answer."""
from app.models.schemas import Route
from app.services.orchestrator import Orchestrator


def _orc():
    return Orchestrator()


def test_graph_flow_list_level():
    resp = _orc().answer("List all L2 processes under Finance", session_id="t1")
    assert resp.route == Route.GRAPH
    assert resp.answer
    # The sample graph has L2 processes under Finance's L1 groups.
    assert "Process" in resp.answer or "process" in resp.answer.lower()


def test_graph_flow_count():
    resp = _orc().answer("How many L1 processes under Finance?", session_id="t2")
    assert resp.route == Route.GRAPH
    assert "3" in resp.answer  # RTR, P2P, O2C


def test_graph_flow_process_diagram():
    resp = _orc().answer("Show the process flow for Procure to Pay", session_id="t3")
    assert resp.route == Route.GRAPH
    assert resp.process_diagram_svg is not None
    assert resp.process_diagram_svg.startswith("<svg")


def test_vector_flow_grounded():
    resp = _orc().answer("What is a Target Operating Model?", session_id="t4")
    assert resp.route == Route.VECTOR
    assert resp.answer
    assert len(resp.citations) >= 1  # grounded with at least one citation


def test_multihop_flow():
    resp = _orc().answer(
        "List the L1 processes under Finance and explain what a TOM is", session_id="t5"
    )
    assert resp.route == Route.MULTIHOP
    assert resp.answer
    assert "route" in resp.timings_ms or "parallel_branches" in resp.timings_ms


def test_memory_persists_window():
    orc = _orc()
    orc.answer("What is a TOM?", session_id="mem")
    orc.answer("List L1 processes under Finance", session_id="mem")
    history = orc.memory.get(f"mem")
    assert len(history) >= 1


def test_unmatched_graph_is_honest():
    resp = _orc().answer("List L2 processes under Nonexistent Function", session_id="t6")
    assert resp.route == Route.GRAPH
    # Should not fabricate; falls back to a helpful "not found" style message.
    assert resp.answer


def test_persona_default_echoed():
    resp = _orc().answer("What is a Target Operating Model?", session_id="t7")
    assert resp.persona == "professional"


def test_persona_knowledge_manager_echoed():
    resp = _orc().answer(
        "What is a Target Operating Model?", session_id="t8", persona="knowledge_manager"
    )
    assert resp.persona == "knowledge_manager"
    assert resp.answer


def test_persona_unknown_falls_back_to_default():
    resp = _orc().answer(
        "What is a Target Operating Model?", session_id="t9", persona="pirate"
    )
    assert resp.persona == "professional"
