"""Neo4j graph backend (prototype/dev). Read-only NL querying via text-to-Cypher.

Process-flow JSON is stored as a string on L1 nodes and parsed with
`apoc.convert.fromJsonMap` (POC gotcha #1) when available, otherwise client-side.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Optional

from app.clients.graph_store import GraphStore
from app.config import Settings
from app.core.logging import get_logger
from app.models.schemas import GraphResult

logger = get_logger(__name__)

_NODE_LABELS = {
    "Process": "Process",
    "Role": "Role",
    "Control": "Control",
    "Policy": "Policy",
}
_EDGE_TYPES = {
    "HAS_SUB_PROCESS",
    "PERFORMED_BY",
    "HAS_CONTROL",
    "GOVERNED_BY",
}


class Neo4jGraphStore(GraphStore):
    def __init__(self, settings: Settings) -> None:
        from neo4j import GraphDatabase

        self.settings = settings
        self._driver = GraphDatabase.driver(
            settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
        )
        from app.services.text_to_cypher import TextToCypher

        self._t2c = TextToCypher()
        self._ensure_schema()

    def _run(self, cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [dict(record) for record in result]

    def _ensure_schema(self) -> None:
        constraints = [
            "CREATE CONSTRAINT process_code_unique IF NOT EXISTS FOR (n:Process) REQUIRE n.code IS UNIQUE",
            "CREATE CONSTRAINT role_code_unique IF NOT EXISTS FOR (n:Role) REQUIRE n.code IS UNIQUE",
            "CREATE CONSTRAINT control_code_unique IF NOT EXISTS FOR (n:Control) REQUIRE n.code IS UNIQUE",
            "CREATE CONSTRAINT policy_code_unique IF NOT EXISTS FOR (n:Policy) REQUIRE n.code IS UNIQUE",
        ]
        for cypher in constraints:
            try:
                self._run(cypher, {})
            except Exception as exc:  # pragma: no cover - older Neo4j editions vary
                logger.info("Neo4j schema statement skipped: %s", exc)

    def natural_language_query(
        self,
        question: str,
        scope: dict[str, str] | None = None,
    ) -> GraphResult:
        rows, cypher = self._t2c.generate_and_execute(question, self._run, scope or {})
        flow = None
        # If a row carries a process_flow_json string, surface it as a flow.
        for row in rows:
            raw = row.get("process_flow_json")
            if isinstance(raw, str):
                try:
                    flow = json.loads(raw)
                    break
                except json.JSONDecodeError:
                    pass
        return GraphResult(rows=rows, query=cypher, process_flow=flow, scope=scope or {})

    def get_process_flow(self, process_name: str) -> Optional[dict[str, Any]]:
        cypher = (
            "MATCH (p:Process {level:1}) WHERE toLower(p.name)=toLower($name) "
            "RETURN p.process_flow_json AS flow LIMIT 1"
        )
        rows = self._run(cypher, {"name": process_name})
        if rows and rows[0].get("flow"):
            return json.loads(rows[0]["flow"])
        return None

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            label = _NODE_LABELS.get(str(node.get("type", "Process")))
            if label:
                normalised = dict(node)
                normalised["name_lc"] = str(normalised.get("name", "")).lower()
                if isinstance(normalised.get("process_flow_json"), (dict, list)):
                    normalised["process_flow_json"] = json.dumps(normalised["process_flow_json"])
                by_type[label].append(normalised)

        for label, rows in by_type.items():
            cypher = (
                f"UNWIND $rows AS r MERGE (n:{label} {{code:r.code}}) "
                "SET n += r, n.name_lc = r.name_lc"
            )
            self._run(cypher, {"rows": rows})
        return len(nodes)

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:
        by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            edge_type = str(edge.get("type", ""))
            if edge_type not in _EDGE_TYPES:
                raise ValueError(f"Unsupported TOM edge type: {edge_type}")
            by_type[edge_type].append(edge)

        for edge_type, rows in by_type.items():
            cypher = (
                "UNWIND $rows AS r "
                "MATCH (a {code:r.from}) MATCH (b {code:r.to}) "
                f"MERGE (a)-[rel:{edge_type}]->(b)"
            )
            self._run(cypher, {"rows": rows})
        return len(edges)

    def close(self) -> None:
        self._driver.close()
