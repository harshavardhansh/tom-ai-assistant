"""Export endpoint: turn an answer (Markdown) into a Word/PPTX/PDF asset."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.security import Principal, get_principal
from app.models.schemas import ExportRequest
from app.services.exporter import Exporter

router = APIRouter(prefix="/api/v1", tags=["export"])
_exporter = Exporter()


@router.post("/export")
async def export(req: ExportRequest, principal: Principal = Depends(get_principal)) -> Response:
    result = _exporter.export(req.answer_markdown, req.title, req.fmt, req.process_flow)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
