"""Metadata/scoping regression tests for multi-vertical readiness."""
from __future__ import annotations

import json
import shutil
from uuid import uuid4
from pathlib import Path

from app.api import routes_ingest
from app.clients.vector_store import LocalVectorStore
from app.services.orchestrator import Orchestrator
from pipeline.document_to_vector import collect
from pipeline.excel_to_graph import build_graph


def _workspace_tmp() -> Path:
    path = (Path("tmp") / "tests" / uuid4().hex).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_graph_build_applies_scope_metadata_and_stable_related_codes():
    rows = [
        {"code": "F", "name": "Finance", "level": "0", "parent_code": "", "roles": "", "controls": ""},
        {
            "code": "F-RTR",
            "name": "Record to Report",
            "level": "1",
            "parent_code": "F",
            "roles": "Finance Manager",
            "controls": "Segregation of Duties",
        },
    ]
    graph, warnings = build_graph(
        rows,
        {},
        {"sector": "Cross-sector", "function": "Finance", "technology": "Tech-agnostic"},
    )

    assert warnings == []
    assert graph["metadata"]["function"] == "Finance"
    for node in graph["nodes"]:
        assert node["function"] == "Finance"
    assert any(n["code"].startswith("ROLE-FM-") for n in graph["nodes"])
    assert any(n["code"].startswith("CTRL-SOD-") for n in graph["nodes"])


def test_vector_collect_uses_deterministic_ids_and_scope_metadata():
    temp_dir = _workspace_tmp()
    try:
        source = temp_dir / "finance_note.md"
        source.write_text("Finance TOM content.\n\nRecord to report details.", encoding="utf-8")

        first = collect(source, "KPMG Confidential", "Cross-sector", "Finance", "Tech-agnostic")
        second = collect(source, "KPMG Confidential", "Cross-sector", "Finance", "Tech-agnostic")

        assert [c["id"] for c in first] == [c["id"] for c in second]
        assert first[0]["content_hash"] == first[0]["id"]
        assert first[0]["function"] == "Finance"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_local_vector_store_filters_by_scope():
    store = LocalVectorStore(data_path=Path("__missing__.json"))
    store.upsert(
        [
            {
                "id": "finance",
                "text": "Record to report and close processes are finance topics.",
                "source": "Finance Guide",
                "classification": "KPMG Confidential",
                "sector": "Cross-sector",
                "function": "Finance",
                "technology": "Tech-agnostic",
            },
            {
                "id": "technology",
                "text": "Cloud platform operations and service management.",
                "source": "Technology Guide",
                "classification": "KPMG Confidential",
                "sector": "Cross-sector",
                "function": "Technology",
                "technology": "Tech-agnostic",
            },
        ]
    )

    results = store.hybrid_search("processes", 5, {"function": "Finance"})

    assert results
    assert {r.function for r in results} == {"Finance"}


def test_graph_ingest_does_not_load_when_validation_warnings(monkeypatch):
    temp_dir = _workspace_tmp()
    try:
        raw = temp_dir / "raw"
        processed = temp_dir / "processed"
        raw.mkdir()
        processed.mkdir()
        (raw / "bad.csv").write_text(
            "code,name,level,parent_code,roles,controls\n"
            "F-BAD,Broken Child,1,UNKNOWN,,\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(routes_ingest, "_roots", lambda: (raw, processed))
        resp = routes_ingest._run_graph(
            routes_ingest.GraphIngestRequest(input_path="bad.csv", function="Finance", load=True)
        )

        assert resp.accepted is False
        assert resp.loaded == 0
        assert resp.warnings
        artifact = Path(resp.artifact or "")
        assert artifact.exists()
        assert json.loads(artifact.read_text(encoding="utf-8"))["metadata"]["function"] == "Finance"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_orchestrator_vector_scope_keeps_finance_sample_grounded():
    resp = Orchestrator().answer(
        "What is Record to Report?",
        session_id="scoped",
        scope={"function": "Finance"},
    )

    assert resp.citations
    assert {c.function for c in resp.citations} == {"Finance"}
