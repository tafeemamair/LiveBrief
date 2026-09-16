"""Command Line Interface for LiveBrief Phase 1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from livebrief.pipeline import LiveBriefPipeline
from livebrief.telemetry.latency import LatencyTracker


def format_response_terminal(response, console: Console) -> None:
    """Format structured grounded response nicely in terminal."""
    console.print()
    console.print(Panel(f"[bold cyan]Query:[/bold cyan] {response.query}", border_style="cyan"))

    # Executive Summary
    summary_style = "green" if response.has_sufficient_evidence else "yellow"
    console.print(
        Panel(
            response.executive_summary,
            title="[bold]Executive Summary[/bold]",
            border_style=summary_style,
        )
    )

    # Key Findings
    if response.key_findings:
        findings_table = Table(title="Key Grounded Findings", show_header=True, header_style="bold magenta")
        findings_table.add_column("#", style="dim", width=4)
        findings_table.add_column("Claim / Finding", style="white")
        findings_table.add_column("Citations", style="cyan", width=12)
        findings_table.add_column("Confidence", style="green", width=12)

        for idx, finding in enumerate(response.key_findings, start=1):
            cites = ", ".join(f"[{c}]" for c in finding.citations)
            findings_table.add_row(
                str(idx),
                finding.claim,
                cites,
                f"{finding.confidence * 100:.1f}%",
            )
        console.print(findings_table)

    # Evidence Ledger
    if response.evidence_ledger:
        ledger_table = Table(title="Evidence Ledger & Citations", show_header=True, header_style="bold blue")
        ledger_table.add_column("Cite", style="bold cyan", width=6)
        ledger_table.add_column("Doc ID", style="dim", width=16)
        ledger_table.add_column("Grounded Excerpt", style="white")
        ledger_table.add_column("Relevance", style="yellow", width=10)

        for item in response.evidence_ledger:
            ledger_table.add_row(
                f"[{item.citation_id}]",
                item.doc_id,
                item.excerpt,
                f"{item.relevance_score:.3f}",
            )
        console.print(ledger_table)

    # Latency Breakdown
    lat_table = Table(title="Measured Latency Instrumentation", show_header=True, header_style="bold green")
    lat_table.add_column("Pipeline Stage", style="cyan")
    lat_table.add_column("Duration", style="bold white")

    lat_table.add_row("Moss Native Retrieval", f"{response.latency.moss_retrieval_ms:.3f} ms")
    lat_table.add_row("Evidence Selection & MMR", f"{response.latency.evidence_selection_ms:.3f} ms")
    lat_table.add_row("Grounded Synthesis", f"{response.latency.synthesis_ms:.3f} ms")
    lat_table.add_row("Total End-to-End Latency", f"[bold green]{response.latency.total_pipeline_ms:.3f} ms[/bold green]")

    console.print(lat_table)
    console.print(f"[dim]Grounding Score: {response.grounding.grounding_score * 100:.1f}% ({response.grounding.supported_claims_count}/{response.grounding.total_claims_count} claims verified)[/dim]\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="LiveBrief - Real-time AI research & briefing engine")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Query command
    query_parser = subparsers.add_parser("query", help="Query knowledge base and generate grounded brief")
    query_parser.add_argument("query", type=str, help="Search query or research question")
    query_parser.add_argument("--files", "-f", nargs="+", required=True, help="Path to document files (.md, .txt, .json)")
    query_parser.add_argument("--top-k", "-k", type=int, default=5, help="Number of evidence chunks to retrieve")
    query_parser.add_argument("--alpha", "-a", type=float, default=0.8, help="Hybrid alpha (0.0=BM25, 1.0=Vector)")

    # Benchmark command
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark Moss retrieval latency on documents")
    bench_parser.add_argument("--files", "-f", nargs="+", required=True, help="Path to document files")
    bench_parser.add_argument("--iterations", "-n", type=int, default=50, help="Number of query iterations")

    # Serve Voice UI command (Phase 2.1)
    voice_parser = subparsers.add_parser("serve-voice", help="Start local web server for LiveBrief Voice Layer")
    voice_parser.add_argument("--port", "-p", type=int, default=8000, help="HTTP port to serve UI on")
    voice_parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface to bind")

    args = parser.parse_args()
    console = Console()

    if args.command == "serve-voice":
        from livebrief.voice.server import serve_voice_ui
        serve_voice_ui(port=args.port, host=args.host)

    elif args.command == "query":
        pipeline = LiveBriefPipeline()
        tracker = LatencyTracker()
        file_paths = [Path(f) for f in args.files]
        count = pipeline.ingest_and_index_files(file_paths, tracker=tracker)
        console.print(f"[green]Indexed {count} chunks into Moss native index.[/green]")

        response = pipeline.query(args.query, tracker=tracker)
        format_response_terminal(response, console)

    elif args.command == "benchmark":
        pipeline = LiveBriefPipeline()
        file_paths = [Path(f) for f in args.files]
        count = pipeline.ingest_and_index_files(file_paths)
        console.print(f"[bold cyan]Running benchmark across {args.iterations} iterations on {count} indexed chunks...[/bold cyan]")

        queries = [
            "What is the system architecture?",
            "What are the latency budgets?",
            "How does Moss retrieval work?",
            "What safeguards prevent hallucinations?",
        ]

        latencies = []
        for i in range(args.iterations):
            q = queries[i % len(queries)]
            resp = pipeline.query(q)
            latencies.append(resp.latency.moss_retrieval_ms)

        avg_lat = sum(latencies) / len(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[int(len(latencies) * 0.50)]
        p95 = latencies_sorted[int(len(latencies) * 0.95)]
        p99 = latencies_sorted[int(len(latencies) * 0.99)]

        console.print(Panel(
            f"[bold]Iterations:[/bold] {args.iterations}\n"
            f"[bold]Average Moss Retrieval Latency:[/bold] {avg_lat:.3f} ms\n"
            f"[bold]p50 (Median):[/bold] {p50:.3f} ms\n"
            f"[bold]p95:[/bold] {p95:.3f} ms\n"
            f"[bold]p99:[/bold] {p99:.3f} ms\n"
            f"[bold]Min / Max:[/bold] {min_lat:.3f} ms / {max_lat:.3f} ms",
            title="[bold green]Moss Retrieval Latency Benchmark[/bold green]",
            border_style="green",
        ))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
