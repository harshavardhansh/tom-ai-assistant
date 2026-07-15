"""Azure Cosmos DB for Apache Gremlin backend (production graph).

Notes on the prod migration from the Neo4j prototype:
  - Cosmos Gremlin has no APOC; process-flow JSON is parsed client-side.
- Vertices carry a partition key (we use the L0 function code, e.g. "F") so
    a function's whole hierarchy is co-located and RU cost stays bounded.
  - For complex NL questions we still generate a traversal via the LLM, but the
    canonical patterns (list/count/roles/controls/flow) use fast-path templates
    below to keep latency and RU usage predictable.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.clients.graph_store import GraphStore
from app.clients.llm_client import LLMClient, LLMUnavailable
from app.config import Settings
from app.core.logging import get_logger
from app.models.schemas import GraphResult

logger = get_logger(__name__)
_LEVEL_RE = re.compile(r"\bl([0-4])\b", re.IGNORECASE)
_NODE_LABELS = {"Process", "Role", "Control", "Policy"}
_EDGE_TYPES = {"HAS_SUB_PROCESS", "PERFORMED_BY", "HAS_CONTROL", "GOVERNED_BY"}
_UNSAFE_GREMLIN = re.compile(
    r"\b(addv|adde|property|drop|sideeffect|aggregate|store|sack|withsideeffect|io|"
    r"inject|call|program|evaluate|system)\b",
    re.IGNORECASE,
)
# Lambda/closure syntax executes arbitrary code server-side; never allow it in
# a generated traversal (read paths only ever need method-chain steps).
_GREMLIN_LAMBDA = re.compile(r"[{}]|->|\blambda\b", re.IGNORECASE)

_GREMLIN_SCHEMA = """Vertices:
- Process {id/code, name, name_lc, level, type, pk, sector, function, technology, process_flow_json}
- Role {id/code, name, name_lc, type, pk, sector, function, technology}
- Control {id/code, name, name_lc, type, pk, sector, function, technology}
- Policy {id/code, name, name_lc, type, pk, sector, function, technology}
Edges:
- Process -HAS_SUB_PROCESS-> Process
- Process -PERFORMED_BY-> Role
- Process -HAS_CONTROL-> Control
- Process -GOVERNED_BY-> Policy
Return valueMap('code','name','level','type','process_flow_json') where possible.
"""


class GremlinGraphStore(GraphStore):
    def __init__(self, settings: Settings) -> None:
        from gremlin_python.driver import client, serializer

        self.settings = settings
        self._client = client.Client(
            settings.gremlin_endpoint,
            "g",
            username=f"/dbs/{settings.gremlin_database}/colls/{settings.gremlin_graph}",
            password=settings.gremlin_key,
            message_serializer=serializer.GraphSONSerializersV2d0(),
        )
        self._llm = LLMClient(settings)

    def _submit(self, query: str, bindings: Optional[dict[str, Any]] = None) -> list[Any]:
        return self._client.submitAsync(query, bindings or {}).result().all().result()

    def natural_language_query(
        self,
        question: str,
        scope: dict[str, str] | None = None,
    ) -> GraphResult:
        scope = scope or {}
        q = question.lower()
        level_match = _LEVEL_RE.search(q)
        anchor = self._anchor_name(q)

        if "process flow" in q or "diagram" in q:
            flow = self._get_process_flow(anchor or question, scope)
            return GraphResult(rows=[{"process": anchor}], query="process_flow", process_flow=flow, scope=scope)

        if level_match and anchor:
            level = int(level_match.group(1))
            rows = self._descendants_at_level(anchor, level, scope)
            if "how many" in q or "count" in q:
                return GraphResult(rows=[{"count": len(rows), "level": level}], query="count", scope=scope)
            return GraphResult(rows=rows, query="list_level", scope=scope)

        if "role" in q and anchor:
            return GraphResult(rows=self._related(anchor, "PERFORMED_BY", scope), query="roles", scope=scope)
        if "control" in q and anchor:
            return GraphResult(rows=self._related(anchor, "HAS_CONTROL", scope), query="controls", scope=scope)

        # Fallback: LLM-generated Gremlin traversal (schema-grounded).
        return self._llm_traversal(question, scope)

    def _descendants_at_level(self, name: str, level: int, scope: dict[str, str]) -> list[dict[str, Any]]:
        scope_steps, bindings = self._scope_steps(scope)
        query = (
            "g.V().has('name_lc', nm)"
            f"{scope_steps}"
            ".repeat(out('HAS_SUB_PROCESS')).emit()"
            f"{scope_steps}"
            ".has('level', lvl).valueMap('code','name','level')"
        )
        bindings.update({"nm": name.lower(), "lvl": level})
        results = self._submit(query, bindings)
        return [self._flatten(v) for v in results]

    def _related(self, name: str, edge: str, scope: dict[str, str]) -> list[dict[str, Any]]:
        scope_steps, bindings = self._scope_steps(scope)
        query = f"g.V().has('name_lc', nm){scope_steps}.out('{edge}').valueMap('code','name')"
        bindings["nm"] = name.lower()
        return [self._flatten(v) for v in self._submit(query, bindings)]

    def get_process_flow(self, process_name: str) -> Optional[dict[str, Any]]:
        return self._get_process_flow(process_name, {})

    def _get_process_flow(self, process_name: str, scope: dict[str, str]) -> Optional[dict[str, Any]]:
        scope_steps, bindings = self._scope_steps(scope)
        query = f"g.V().has('level',1).has('name_lc', nm){scope_steps}.values('process_flow_json')"
        bindings["nm"] = process_name.lower()
        rows = self._submit(query, bindings)
        if rows:
            raw = rows[0]
            return json.loads(raw) if isinstance(raw, str) else raw
        return None

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        for node in nodes:
            label = str(node.get("type", "Process"))
            if label not in _NODE_LABELS:
                raise ValueError(f"Unsupported TOM node type: {label}")
            code = str(node["code"])
            payload = dict(node)
            payload["type"] = label
            payload["name_lc"] = str(payload.get("name", "")).lower()
            payload["pk"] = self._partition_key(payload)
            if isinstance(payload.get("process_flow_json"), (dict, list)):
                payload["process_flow_json"] = json.dumps(payload["process_flow_json"])

            query = (
                f"g.V(id).fold().coalesce(unfold(), "
                f"addV('{label}').property('id', id).property('code', id).property('pk', pk))"
                ".property('type', typ)"
                ".property('name', name)"
                ".property('name_lc', name_lc)"
            )
            bindings: dict[str, Any] = {
                "id": code,
                "pk": payload["pk"],
                "typ": label,
                "name": payload.get("name", ""),
                "name_lc": payload["name_lc"],
            }
            if "level" in payload:
                query += ".property('level', level)"
                bindings["level"] = int(payload["level"])
            if "process_flow_json" in payload:
                query += ".property('process_flow_json', flow)"
                bindings["flow"] = payload["process_flow_json"]
            for key in ("sector", "function", "technology"):
                if payload.get(key):
                    binding_key = f"meta_{key}"
                    query += f".property('{key}', {binding_key})"
                    bindings[binding_key] = payload[key]
            self._submit(query, bindings)
        return len(nodes)

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:
        for edge in edges:
            edge_type = str(edge.get("type", ""))
            if edge_type not in _EDGE_TYPES:
                raise ValueError(f"Unsupported TOM edge type: {edge_type}")
            query = (
                f"g.V(src).outE('{edge_type}').where(inV().hasId(dst)).fold()"
                f".coalesce(unfold(), g.V(src).addE('{edge_type}').to(g.V(dst)))"
            )
            self._submit(query, {"src": edge["from"], "dst": edge["to"]})
        return len(edges)

    def _llm_traversal(self, question: str, scope: dict[str, str]) -> GraphResult:  # pragma: no cover - needs Cosmos + LLM
        if not self._llm.available:
            logger.info("No fast-path matched and Workbench LLM unavailable for: %s", question)
            return GraphResult(rows=[], query="unmatched", scope=scope)
        try:
            scope_text = f"\nScope filters to apply when present: {json.dumps(scope)}" if scope else ""
            data = self._llm.chat_json(
                "You generate read-only Apache TinkerPop Gremlin traversals for Azure Cosmos DB. "
                "Return JSON only with keys traversal and rationale. Never emit writes, mutations, "
                "lambdas, side effects, imports, or multiple statements.",
                f"Schema:\n{_GREMLIN_SCHEMA}{scope_text}\nQuestion: {question}\n"
                "Return one traversal starting with g.V() and ending with valueMap(...) or count().",
            )
            traversal = str(data["traversal"]).strip()
            self._assert_read_only(traversal)
            rows = self._submit(traversal, {})
            normalised = [
                self._flatten(r) if isinstance(r, dict) else {"value": r}
                for r in rows
            ]
            flow = None
            for row in normalised:
                raw = row.get("process_flow_json")
                if isinstance(raw, str):
                    flow = json.loads(raw)
                    break
            return GraphResult(rows=normalised, query=traversal, process_flow=flow, scope=scope)
        except (LLMUnavailable, Exception) as exc:
            logger.info("LLM Gremlin traversal failed for %s: %s", question, exc)
            return GraphResult(rows=[], query="unmatched", scope=scope)

    @staticmethod
    def _assert_read_only(traversal: str) -> None:
        text = traversal.strip()
        if not text.startswith("g.V(") and not text.startswith("g.V()"):
            raise ValueError("Traversal must start with g.V()")
        if ";" in text or "\n" in text or _UNSAFE_GREMLIN.search(text):
            raise ValueError("Traversal contains unsafe Gremlin operation")
        if _GREMLIN_LAMBDA.search(text):
            raise ValueError("Traversal contains a lambda/closure, which is not allowed")

    @staticmethod
    def _scope_steps(scope: dict[str, str]) -> tuple[str, dict[str, Any]]:
        steps = []
        bindings: dict[str, Any] = {}
        for key in ("sector", "function", "technology"):
            value = scope.get(key)
            if value:
                binding_key = f"scope_{key}"
                steps.append(f".has('{key}', {binding_key})")
                bindings[binding_key] = value
        return "".join(steps), bindings

    @staticmethod
    def _anchor_name(q: str) -> Optional[str]:
        m = re.search(r"(?:under|in|of|for|within)\s+([a-z0-9 &\-]+?)\s*(?:\?|$|and\b)", q)
        return m.group(1).strip() if m else None

    @staticmethod
    def _flatten(valuemap: dict[str, Any]) -> dict[str, Any]:
        return {k: (v[0] if isinstance(v, list) and v else v) for k, v in valuemap.items()}

    @staticmethod
    def _partition_key(node: dict[str, Any]) -> str:
        code = str(node.get("code", ""))
        if code.startswith(("ROLE-", "CTRL-", "POL-")):
            return "shared"
        return code.split("-")[0] if code else "unknown"

    def close(self) -> None:
        self._client.close()
