"""Tests for LiveBrief CLI commands."""

from pathlib import Path
import pytest
from livebrief.cli import main


def test_cli_query(monkeypatch, capsys, tmp_path: Path):
    doc_path = tmp_path / "cli_sample.md"
    doc_path.write_text("# LiveBrief System\n\nLiveBrief uses Moss for hot-path semantic retrieval.", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["livebrief", "query", "What does LiveBrief use?", "--files", str(doc_path)])
    main()

    captured = capsys.readouterr()
    assert "LiveBrief" in captured.out
    assert "Executive Summary" in captured.out
    assert "Measured Latency Instrumentation" in captured.out


def test_cli_benchmark(monkeypatch, capsys, tmp_path: Path):
    doc_path = tmp_path / "bench_sample.md"
    doc_path.write_text("# Benchmark Document\n\nLatency budget is strictly under 10 milliseconds.", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["livebrief", "benchmark", "--files", str(doc_path), "--iterations", "5"])
    main()

    captured = capsys.readouterr()
    assert "Moss Retrieval Latency Benchmark" in captured.out
    assert "Average Moss Retrieval Latency" in captured.out
