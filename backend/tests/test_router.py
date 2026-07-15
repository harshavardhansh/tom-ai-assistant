"""Router classification tests (offline; keyword layer)."""
from app.models.schemas import Route
from app.services.router import QueryRouter


def test_graph_routing():
    r = QueryRouter()
    assert r.route("List all L2 processes under Finance").route == Route.GRAPH
    assert r.route("How many L3 processes under Record to Report?").route == Route.GRAPH
    assert r.route("Show the process flow for Procure to Pay").route == Route.GRAPH


def test_vector_routing():
    r = QueryRouter()
    assert r.route("What is a Target Operating Model?").route == Route.VECTOR
    assert r.route("Explain the difference between tech-agnostic and tech-specific TOM").route == Route.VECTOR


def test_multihop_routing():
    r = QueryRouter()
    d = r.route("List L2 Finance processes and explain what a TOM is")
    assert d.route == Route.MULTIHOP
    assert d.confidence > 0.5
