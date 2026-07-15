"""Request/response schemas (API contract) and internal domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Route(str, Enum):
    GRAPH = "GRAPH"
    VECTOR = "VECTOR"
    MULTIHOP = "MULTIHOP"


# ---------------------------------------------------------------------------
# API contract
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    session_id: str = Field("default", max_length=128)
    # Chat persona (approved L2 architecture: "TOM Chat Personas will be shown
    # in UI Prompt"). Unknown values fall back to the default persona.
    persona: str = Field("professional", max_length=64)
    sector: Optional[str] = Field(None, max_length=128)
    function: Optional[str] = Field(None, max_length=128)
    technology: Optional[str] = Field(None, max_length=128)

    @property
    def scope(self) -> dict[str, str]:
        return {
            k: v.strip()
            for k, v in {
                "sector": self.sector,
                "function": self.function,
                "technology": self.technology,
            }.items()
            if v and v.strip()
        }


class Citation(BaseModel):
    label: str
    source: str
    locator: Optional[str] = None  # e.g. "p. 12" or node code "F-RTR-2"
    classification: str = "KPMG Confidential"
    sector: Optional[str] = None
    function: Optional[str] = None
    technology: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    route: Route
    confidence: float
    persona: str = "professional"
    citations: list[Citation] = []
    suggested_questions: list[str] = []
    process_diagram_svg: Optional[str] = None
    process_flow: Optional[dict[str, Any]] = None
    timings_ms: dict[str, float] = {}
    session_id: str = "default"


class ExportRequest(BaseModel):
    answer_markdown: str
    title: str = "TOM AI Assistant — Response"
    fmt: str = Field("docx", pattern="^(docx|pptx|pdf)$")
    process_flow: Optional[dict[str, Any]] = None  # optional flow JSON to diagram


# ---------------------------------------------------------------------------
# Internal domain types
# ---------------------------------------------------------------------------
@dataclass
class RetrievedChunk:
    """A passage returned from the vector store."""
    text: str
    source: str
    locator: Optional[str] = None
    classification: str = "KPMG Confidential"
    sector: Optional[str] = None
    function: Optional[str] = None
    technology: Optional[str] = None
    score: float = 0.0


@dataclass
class GraphResult:
    """Structured result returned from the graph store."""
    rows: list[dict[str, Any]] = field(default_factory=list)
    query: str = ""
    process_flow: Optional[dict[str, Any]] = None
    scope: dict[str, str] = field(default_factory=dict)


@dataclass
class SubQuestion:
    text: str
    route: Route


@dataclass
class BranchResult:
    sub_question: str
    route: Route
    narrative: str
    citations: list[Citation] = field(default_factory=list)
    process_flow: Optional[dict[str, Any]] = None


@dataclass
class QAExchange:
    question: str
    answer: str
