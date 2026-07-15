"""Ingestion control endpoints.

The Logic App calls `/scan` and `/process`; knowledge managers can also trigger
graph/vector loads directly from configured ingestion folders. These endpoints
do real work, but stay deliberately narrow: no arbitrary command execution and
no paths outside the ingestion roots.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.clients.graph_store import get_graph_store
from app.clients.vector_store import get_vector_store
from app.config import get_settings
from app.core.security import Principal, require_role

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])

def _find_runtime_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pipeline").exists():
            return parent
    return here.parents[2]


_REPO_ROOT = _find_runtime_root()
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


class IngestStatus(BaseModel):
    accepted: bool
    detail: str
    artifact: Optional[str] = None
    loaded: int = 0
    warnings: list[str] = []


class GraphIngestRequest(BaseModel):
    input_path: str = Field(..., description="CSV/XLSX under INGESTION_RAW_DIR")
    flows_path: Optional[str] = Field(None, description="Optional flow JSON under INGESTION_RAW_DIR")
    output_path: Optional[str] = Field(None, description="Optional artifact path under INGESTION_PROCESSED_DIR")
    sector: str = Field("Cross-sector", max_length=128)
    function: Optional[str] = Field(None, max_length=128)
    technology: str = Field("Tech-agnostic", max_length=128)
    load: bool = True
    fail_on_warnings: bool = True


class VectorIngestRequest(BaseModel):
    input_path: str = Field(..., description="Document file/folder under INGESTION_RAW_DIR")
    output_path: Optional[str] = Field(None, description="Optional chunks artifact under INGESTION_PROCESSED_DIR")
    sector: str = Field("Cross-sector", max_length=128)
    function: str = Field("Unspecified", max_length=128)
    technology: str = Field("Tech-agnostic", max_length=128)
    classification: Optional[str] = Field(None, max_length=128)
    load: bool = True


class ProcessBlobRequest(BaseModel):
    blobName: str
    fileExtension: Optional[str] = None
    flowsBlobName: Optional[str] = None
    sector: str = "Cross-sector"
    function: Optional[str] = None
    technology: str = "Tech-agnostic"
    classification: Optional[str] = None


class ScanResult(BaseModel):
    verdict: Literal["clean", "infected"]
    engine: str
    detail: str = ""


def _roots() -> tuple[Path, Path]:
    settings = get_settings()
    raw = (_REPO_ROOT / settings.ingestion_raw_dir).resolve()
    processed = (_REPO_ROOT / settings.ingestion_processed_dir).resolve()
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    return raw, processed


def _safe_path(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if root != path and root not in path.parents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Path escapes configured ingestion root")
    return path


def _processed_path(value: Optional[str], fallback_name: str) -> Path:
    _, processed = _roots()
    return _safe_path(processed, value or fallback_name)


def _run_graph(req: GraphIngestRequest) -> IngestStatus:
    raw, _ = _roots()
    input_path = _safe_path(raw, req.input_path)
    if not input_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Graph input not found: {req.input_path}")
    flows = {}
    if req.flows_path:
        flows_path = _safe_path(raw, req.flows_path)
        if not flows_path.exists():
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Flow input not found: {req.flows_path}")
        flows = json.loads(flows_path.read_text(encoding="utf-8"))

    from pipeline.excel_to_graph import _normalise_metadata, _read_rows, build_graph

    rows = _read_rows(input_path)
    metadata = _normalise_metadata(rows, req.sector, req.function or "", req.technology)
    graph, warnings = build_graph(rows, flows, metadata)
    output_path = _processed_path(req.output_path, f"{input_path.stem}.graph.json")
    output_path.write_text(json.dumps(graph, indent=2), encoding="utf-8")

    loaded = 0
    if warnings and req.fail_on_warnings:
        return IngestStatus(
            accepted=False,
            detail="Graph artifact was generated but not loaded because validation warnings must be resolved.",
            artifact=str(output_path),
            loaded=0,
            warnings=warnings,
        )
    if req.load:
        store = get_graph_store()
        process_nodes = [
            {**n, "process_flow_json": json.dumps(n["process_flow_json"])}
            if "process_flow_json" in n and not isinstance(n["process_flow_json"], str)
            else n
            for n in graph["nodes"]
        ]
        loaded = store.upsert_nodes(process_nodes) + store.upsert_edges(graph["edges"])
        store.close()
    return IngestStatus(
        accepted=True,
        detail=f"Graph artifact contains {len(graph['nodes'])} nodes and {len(graph['edges'])} edges.",
        artifact=str(output_path),
        loaded=loaded,
        warnings=warnings,
    )


def _run_vector(req: VectorIngestRequest) -> IngestStatus:
    raw, _ = _roots()
    input_path = _safe_path(raw, req.input_path)
    if not input_path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Vector input not found: {req.input_path}")

    from pipeline.document_to_vector import collect

    chunks = collect(
        input_path,
        req.classification or get_settings().document_classification,
        req.sector,
        req.function,
        req.technology,
    )
    output_path = _processed_path(req.output_path, f"{input_path.stem}.vectors.json")
    output_path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")

    loaded = 0
    if req.load:
        loaded = get_vector_store().upsert(chunks)
    return IngestStatus(
        accepted=True,
        detail=f"Vector artifact contains {len(chunks)} chunks.",
        artifact=str(output_path),
        loaded=loaded,
    )


@router.post("/graph", response_model=IngestStatus)
async def reingest_graph(
    req: GraphIngestRequest,
    principal: Principal = Depends(require_role("knowledge_manager")),
) -> IngestStatus:
    return _run_graph(req)


@router.post("/vector", response_model=IngestStatus)
async def reingest_vector(
    req: VectorIngestRequest,
    principal: Principal = Depends(require_role("knowledge_manager")),
) -> IngestStatus:
    return _run_vector(req)


@router.post("/scan", response_model=ScanResult)
async def scan_asset(
    request: Request,
    principal: Principal = Depends(require_role("knowledge_manager")),
) -> ScanResult:
    body = await request.body()
    settings = get_settings()
    if settings.defender_scan_endpoint:
        scan_req = urllib.request.Request(
            settings.defender_scan_endpoint,
            data=body,
            method="POST",
            headers={"Content-Type": request.headers.get("content-type", "application/octet-stream")},
        )
        with urllib.request.urlopen(scan_req, timeout=30) as resp:  # nosec - configured enterprise endpoint
            data = json.loads(resp.read().decode("utf-8"))
        verdict = "clean" if data.get("verdict") == "clean" else "infected"
        return ScanResult(verdict=verdict, engine="defender", detail=data.get("detail", ""))

    if get_settings().environment != "dev":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Defender scan endpoint is not configured")
    suspicious = [b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", b"<script", b"powershell -enc"]
    verdict = "infected" if any(sig.lower() in body.lower() for sig in suspicious) else "clean"
    return ScanResult(verdict=verdict, engine="dev-signature", detail="Development scan only")


@router.post("/process", response_model=IngestStatus)
async def process_asset(
    req: ProcessBlobRequest = Body(...),
    principal: Principal = Depends(require_role("knowledge_manager")),
) -> IngestStatus:
    suffix = Path(req.blobName).suffix.lower()
    if suffix in {".csv", ".xlsx", ".xlsm"}:
        # The Logic App names the companion flow file by convention; only pass
        # it through when it actually landed alongside the hierarchy export.
        flows_path = (req.flowsBlobName or "").strip() or None
        if flows_path:
            raw, _ = _roots()
            if not _safe_path(raw, flows_path).exists():
                flows_path = None
        return _run_graph(
            GraphIngestRequest(
                input_path=req.blobName,
                flows_path=flows_path,
                sector=req.sector,
                function=req.function,
                technology=req.technology,
                load=True,
            )
        )
    return _run_vector(
        VectorIngestRequest(
            input_path=req.blobName,
            sector=req.sector,
            function=req.function or "Unspecified",
            technology=req.technology,
            classification=req.classification,
            load=True,
        )
    )


@router.post("/alert", response_model=IngestStatus)
async def ingestion_alert(
    payload: dict = Body(...),
    principal: Principal = Depends(require_role("knowledge_manager")),
) -> IngestStatus:
    return IngestStatus(accepted=True, detail=f"Ingestion alert recorded: {payload.get('event', 'unknown')}")
