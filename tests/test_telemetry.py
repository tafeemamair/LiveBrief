"""Tests for latency instrumentation and telemetry."""

import time
import pytest
from livebrief.telemetry.latency import LatencyTracker, StageTimer


def test_stage_timer_measures_elapsed():
    timer = StageTimer("test_stage")
    with timer:
        time.sleep(0.01)  # 10ms

    assert timer.elapsed_ms >= 8.0  # Allow slight timing tolerance


def test_latency_tracker_breakdown():
    tracker = LatencyTracker()

    with tracker.measure("moss_retrieval"):
        time.sleep(0.005)

    with tracker.measure("evidence_selection"):
        time.sleep(0.003)

    breakdown = tracker.get_breakdown()

    assert breakdown.moss_retrieval_ms >= 3.0
    assert breakdown.evidence_selection_ms >= 2.0
    assert breakdown.total_pipeline_ms >= breakdown.moss_retrieval_ms + breakdown.evidence_selection_ms

    summary = breakdown.summary()
    assert "moss_retrieval" in summary
    assert "ms" in summary["moss_retrieval"]
