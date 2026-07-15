"""FastAPI application entry point for the TOM AI Knowledge Assistant."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_chat, routes_export, routes_health, routes_ingest
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.telemetry import init_telemetry


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    init_telemetry()

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="Conversational access to KPMG Target Operating Model knowledge "
        "(graph hierarchy + document retrieval) with grounded synthesis.",
    )

    allow_origins = ["*"] if settings.environment == "dev" else settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(routes_health.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_export.router)
    app.include_router(routes_ingest.router)
    return app


app = create_app()
