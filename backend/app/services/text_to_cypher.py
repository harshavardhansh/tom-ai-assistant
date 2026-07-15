"""Text-to-Cypher / Text-to-Gremlin generation (Brain 1 core).

Safety model (defence in depth):
  1. Prompt forbids any write/admin clause.
  2. `assert_read_only` rejects queries containing write keywords.
  3. Generation binds user literals as parameters (injection-safe).
  4. A self-repair loop re-prompts on execution error (bounded retries).
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from app.clients.llm_client import LLMClient, LLMUnavailable
from app.core.logging import get_logger
from app.prompts import templates as P

logger = get_logger(__name__)

# Canonical schema injected into the prompt. Mirrors the Finance ontology.
GRAPH_SCHEMA = """Nodes:
  (:Process {code, name, level, sector, function, technology})  // level 0..4, code is unique
  (:Role {code, name, sector, function, technology})
  (:Control {code, name, sector, function, technology})
  (:Policy {code, name, sector, function, technology})
L1 Process nodes also have property `process_flow_json` (a JSON string).

Relationships:
  (:Process)-[:HAS_SUB_PROCESS]->(:Process)  // parent level -> child level
  (:Process)-[:PERFORMED_BY]->(:Role)
  (:Process)-[:HAS_CONTROL]->(:Control)
  (:Process)-[:GOVERNED_BY]->(:Policy)
"""

_WRITE = re.compile(
    r"\b(create|merge|set|delete|remove|drop|detach|load\s+csv|foreach|"
    r"call\s+(db|dbms|tx|sys)\.|"
    r"apoc\.(create|merge|refactor|load|periodic|trigger|export|import|cypher)|"
    r"using\s+periodic\s+commit)\b",
    re.IGNORECASE,
)


class UnsafeQueryError(RuntimeError):
    pass


def assert_read_only(cypher: str) -> None:
    if _WRITE.search(cypher):
        raise UnsafeQueryError("Generated query contained a write/admin clause")


class TextToCypher:
    def __init__(self, llm: Optional[LLMClient] = None, max_repairs: int = 2) -> None:
        self.llm = llm or LLMClient()
        self.max_repairs = max_repairs

    def generate(
        self,
        question: str,
        scope: dict[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        if not self.llm.available:
            raise LLMUnavailable("Text-to-Cypher requires the Workbench LLM")
        scope_text = f"\nApply these exact scope filters when present: {scope}" if scope else ""
        data = self.llm.chat_json(
            P.CYPHER_SYSTEM.format(schema=GRAPH_SCHEMA),
            P.CYPHER_USER.format(question=f"{question}{scope_text}"),
        )
        cypher, params = data["cypher"], data.get("params", {})
        assert_read_only(cypher)
        return cypher, params

    def generate_and_execute(
        self,
        question: str,
        executor: Callable[[str, dict[str, Any]], list[dict[str, Any]]],
        scope: dict[str, str] | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Generate, run via `executor`, self-repair on error."""
        scope = scope or {}
        cypher, params = self.generate(question, scope)
        last_error = ""
        for attempt in range(self.max_repairs + 1):
            try:
                return executor(cypher, params), cypher
            except Exception as exc:  # execution error -> repair
                last_error = str(exc)
                logger.info("Cypher attempt %d failed: %s", attempt + 1, last_error)
                if attempt >= self.max_repairs:
                    break
                repaired = self.llm.chat_json(
                    P.CYPHER_SYSTEM.format(schema=GRAPH_SCHEMA),
                    P.CYPHER_REPAIR.format(
                        error=f"{last_error}; scope filters: {scope}",
                        cypher=cypher,
                    ),
                )
                cypher, params = repaired["cypher"], repaired.get("params", {})
                assert_read_only(cypher)
        raise RuntimeError(f"Query failed after repairs: {last_error}")
