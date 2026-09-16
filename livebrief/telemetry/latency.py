"""Sub-millisecond latency instrumentation and stage timer for LiveBrief."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict, Generator, Optional
from livebrief.models.response import LatencyBreakdown


class StageTimer:
    """High-resolution wall-clock timer for an individual stage."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.start_time: Optional[float] = None
        self.elapsed_ms: float = 0.0

    def start(self) -> None:
        self.start_time = time.perf_counter()

    def stop(self) -> float:
        if self.start_time is not None:
            self.elapsed_ms = (time.perf_counter() - self.start_time) * 1000.0
        return self.elapsed_ms

    def __enter__(self) -> "StageTimer":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class LatencyTracker:
    """Collects and aggregates timing across all pipeline execution stages."""

    def __init__(self) -> None:
        self._timings: Dict[str, float] = {
            "ingestion": 0.0,
            "indexing": 0.0,
            "moss_retrieval": 0.0,
            "evidence_selection": 0.0,
            "synthesis": 0.0,
        }
        self._pipeline_start: float = time.perf_counter()

    def record(self, stage: str, elapsed_ms: float) -> None:
        """Record elapsed time in milliseconds for a given stage."""
        self._timings[stage] = elapsed_ms

    @contextmanager
    def measure(self, stage: str) -> Generator[StageTimer, None, None]:
        """Context manager to measure and record a pipeline stage."""
        timer = StageTimer(stage)
        timer.start()
        try:
            yield timer
        finally:
            timer.stop()
            self._timings[stage] = timer.elapsed_ms

    def get_breakdown(self, total_elapsed_ms: Optional[float] = None) -> LatencyBreakdown:
        """Build LatencyBreakdown model."""
        e2e = total_elapsed_ms if total_elapsed_ms is not None else (time.perf_counter() - self._pipeline_start) * 1000.0
        return LatencyBreakdown(
            ingestion_ms=self._timings.get("ingestion", 0.0),
            indexing_ms=self._timings.get("indexing", 0.0),
            moss_retrieval_ms=self._timings.get("moss_retrieval", 0.0),
            evidence_selection_ms=self._timings.get("evidence_selection", 0.0),
            synthesis_ms=self._timings.get("synthesis", 0.0),
            total_pipeline_ms=e2e,
        )
