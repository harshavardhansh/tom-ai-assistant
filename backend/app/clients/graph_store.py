"""Graph knowledge layer (Brain 1).

A single `GraphStore` interface with three backends:
  - memory:  offline structured store (loads sample finance graph; answers the
             canonical question patterns without an LLM or a database).
  - neo4j:   prototype/dev (text-to-Cypher).
  - gremlin: production (Azure Cosmos DB for Apache Gremlin).

Switching backends is config-only (`GRAPH_BACKEND`).
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.paths import find_sample_data
from app.models.schemas import GraphResult

logger = get_logger(__name__)

_LEVEL_RE = re.compile(r"\bl([0-4])\b", re.IGNORECASE)
_SAMPLE = find_sample_data("finance_graph.json")


class GraphStore(ABC):
    @abstractmethod
    def natural_language_query(
        self,
        question: str,
        scope: dict[str, str] | None = None,
    ) -> GraphResult: ...

    @abstractmethod
    def get_process_flow(self, process_name: str) -> Optional[dict[str, Any]]: ...

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:  # pragma: no cover
        raise NotImplementedError

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:  # pragma: no cover
        raise NotImplementedError

    def close(self) -> None:  # pragma: no cover
        pass


class InMemoryGraphStore(GraphStore):
    """Deterministic offline store. Not a query engine — it recognises the
    canonical TOM question patterns the POC demonstrates."""

    def __init__(self, data_path: Optional[Path] = None) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.children: dict[str, list[str]] = defaultdict(list)
        self.edges_by_type: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        path = data_path or _SAMPLE
        if path and path.exists():
            self._load(json.loads(path.read_text(encoding="utf-8-sig")))
        else:
            logger.warning("Sample finance graph not found (looked for finance_graph.json under pipeline/sample_data); graph is empty")

    def _load(self, data: dict[str, Any]) -> None:
        metadata = {
            k: v
            for k, v in data.get("metadata", {}).items()
            if k in {"sector", "function", "technology"} and v
        }
        for n in data.get("nodes", []):
            node = dict(n)
            for key, value in metadata.items():
                node.setdefault(key, value)
            self.nodes[n["code"]] = node
        for e in data.get("edges", []):
            self.edges_by_type[e["type"]][e["from"]].append(e["to"])
            if e["type"] == "HAS_SUB_PROCESS":
                self.children[e["from"]].append(e["to"])

    # -- helpers ---------------------------------------------------------
    def _find_by_name(
        self,
        name: str,
        scope: dict[str, str] | None = None,
    ) -> Optional[dict[str, Any]]:
        name = name.strip().lower()
        for node in self.nodes.values():
            if node.get("name", "").lower() == name and self._matches_scope(node, scope):
                return node
        for node in self.nodes.values():  # fall back to substring
            if name and name in node.get("name", "").lower() and self._matches_scope(node, scope):
                return node
        return None

    @staticmethod
    def _matches_scope(node: dict[str, Any], scope: dict[str, str] | None) -> bool:
        if not scope:
            return True
        for key, value in scope.items():
            if value and str(node.get(key, "")).lower() != value.lower():
                return False
        return True

    def _descendants_at_level(
        self,
        root_code: str,
        level: int,
        scope: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        out, stack, seen = [], [root_code], set()
        while stack:
            code = stack.pop()
            if code in seen:
                continue
            seen.add(code)
            for child in self.children.get(code, []):
                node = self.nodes.get(child)
                if not node:
                    continue
                if node.get("level") == level and self._matches_scope(node, scope):
                    out.append(node)
                stack.append(child)
        return sorted(out, key=lambda n: n.get("code", ""))

    def _related(self, code: str, edge_type: str) -> list[dict[str, Any]]:
        return [self.nodes[t] for t in self.edges_by_type[edge_type].get(code, []) if t in self.nodes]

    # -- interface -------------------------------------------------------
    def natural_language_query(
        self,
        question: str,
        scope: dict[str, str] | None = None,
    ) -> GraphResult:
        scope = scope or {}
        q = question.lower()
        level_match = _LEVEL_RE.search(q)

        # "... under <process>" or "... in <process>"
        anchor_match = re.search(r"(?:under|in|of|for|within)\s+([a-z0-9 &\-]+?)\s*(?:\?|$|and\b)", q)
        anchor_node = self._find_by_name(anchor_match.group(1), scope) if anchor_match else None

        # process-flow request
        if "process flow" in q or "flow for" in q or "diagram" in q:
            target = anchor_node or self._find_by_name(question, scope)
            if target and self._matches_scope(target, scope):
                flow = self._flow_for(target)
                return GraphResult(rows=[{"process": target["name"]}], query="process_flow",
                                   process_flow=flow, scope=scope)

        # roles / controls
        if "role" in q and anchor_node:
            roles = self._related(anchor_node["code"], "PERFORMED_BY")
            return GraphResult(rows=[{"role": r["name"]} for r in roles], query="roles", scope=scope)
        if "control" in q and anchor_node:
            controls = self._related(anchor_node["code"], "HAS_CONTROL")
            return GraphResult(rows=[{"control": c["name"]} for c in controls], query="controls", scope=scope)

        # list / count at level
        if level_match:
            level = int(level_match.group(1))
            root = anchor_node["code"] if anchor_node else self._root_code(scope)
            nodes = self._descendants_at_level(root, level, scope)
            if "how many" in q or "count" in q or "number of" in q:
                return GraphResult(rows=[{"count": len(nodes), "level": level}], query="count", scope=scope)
            return GraphResult(
                rows=[{"code": n["code"], "name": n["name"], "level": n["level"]} for n in nodes],
                query="list_level",
                scope=scope,
            )

        # children of a named process (no explicit level)
        if anchor_node:
            kids = [
                self.nodes[c]
                for c in self.children.get(anchor_node["code"], [])
                if self._matches_scope(self.nodes[c], scope)
            ]
            return GraphResult(
                rows=[{"code": n["code"], "name": n["name"], "level": n["level"]} for n in kids],
                query="children",
                scope=scope,
            )

        return GraphResult(rows=[], query="unmatched", scope=scope)

    def get_process_flow(self, process_name: str) -> Optional[dict[str, Any]]:
        node = self._find_by_name(process_name)
        return self._flow_for(node) if node else None

    def _flow_for(self, node: dict[str, Any]) -> Optional[dict[str, Any]]:
        flow = node.get("process_flow_json")
        if isinstance(flow, str):  # stored as JSON string (POC gotcha #1)
            flow = json.loads(flow)
        return flow

    def _root_code(self, scope: dict[str, str] | None = None) -> str:
        if scope and scope.get("function"):
            for code, n in self.nodes.items():
                if n.get("level") == 0 and str(n.get("name", "")).lower() == scope["function"].lower():
                    return code
        for code, n in self.nodes.items():
            if n.get("level") == 0 and self._matches_scope(n, scope):
                return code
        return next(iter(self.nodes), "")

    # -- ingestion (used by pipeline in dev) -----------------------------
    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> int:
        for n in nodes:
            self.nodes[n["code"]] = n
        return len(nodes)

    def upsert_edges(self, edges: list[dict[str, Any]]) -> int:
        for e in edges:
            self.edges_by_type[e["type"]][e["from"]].append(e["to"])
            if e["type"] == "HAS_SUB_PROCESS":
                self.children[e["from"]].append(e["to"])
        return len(edges)


def get_graph_store(settings: Optional[Settings] = None) -> GraphStore:
    settings = settings or get_settings()
    backend = settings.graph_backend
    if backend == "neo4j":
        from app.clients.graph_neo4j import Neo4jGraphStore

        return Neo4jGraphStore(settings)
    if backend == "gremlin":
        from app.clients.graph_gremlin import GremlinGraphStore

        return GremlinGraphStore(settings)
    return InMemoryGraphStore()
