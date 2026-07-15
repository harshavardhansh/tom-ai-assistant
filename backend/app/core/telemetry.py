"""Telemetry: distributed tracing + a simple stage-timer used to populate the
`timings_ms` on responses (latency is a tracked SLO). If Azure Monitor /
OpenTelemetry packages are absent, this degrades to a no-op so dev is unaffected.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from app.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def init_telemetry() -> None:
    settings = get_settings()
    if settings.environment == "dev":
        return
    try:  # pragma: no cover - optional dependency
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(logger_name="tom")
        logger.info("Azure Monitor telemetry configured")
    except Exception as exc:  # pragma: no cover
        logger.info("Telemetry not configured (%s); continuing", exc)


class StageTimer:
    """Collects per-stage latencies in milliseconds."""

    def __init__(self) -> None:
        self.timings_ms: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.timings_ms[name] = round((time.perf_counter() - start) * 1000, 1)
