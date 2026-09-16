"""End-to-End integration tests for LiveBrief Phase 1 Retrieval Vertical Slice."""

from pathlib import Path
import pytest
from livebrief.models.query import QueryRequest
from livebrief.pipeline import LiveBriefPipeline
from livebrief.telemetry.latency import LatencyTracker


@pytest.fixture
def sample_knowledge_file() -> Path:
    path = Path("samples/sample_knowledge.md")
    assert path.exists(), f"Sample knowledge document not found at {path}"
    return path


def test_e2e_pipeline_with_real_knowledge_doc(sample_knowledge_file: Path):
    pipeline = LiveBriefPipeline(index_name="e2e_livebrief")
    tracker = LatencyTracker()

    # 1. Ingest & Index
    indexed_count = pipeline.ingest_and_index_files([sample_knowledge_file], tracker=tracker)
    assert indexed_count > 0
    assert pipeline.indexer.doc_count == indexed_count

    # 2. Query for real architectural facts
    req = QueryRequest(
        query="What is the latency budget and retrieval mechanism for LiveBrief?",
        top_k=3,
        alpha=0.8,
    )
    response = pipeline.query(req, tracker=tracker)

    # 3. Assertions on structured grounded response
    assert response.has_sufficient_evidence is True
    assert len(response.key_findings) > 0
    assert len(response.evidence_ledger) > 0
    assert response.grounding.grounding_score == 1.0

    # Ensure citations are properly linked
    citation_ids = {item.citation_id for item in response.evidence_ledger}
    for finding in response.key_findings:
        assert len(finding.citations) > 0
        for cite_id in finding.citations:
            assert cite_id in citation_ids

    # 4. Latency verification
    assert response.latency.moss_retrieval_ms > 0.0
    assert response.latency.evidence_selection_ms >= 0.0
    assert response.latency.synthesis_ms >= 0.0
    assert response.latency.total_pipeline_ms > 0.0

    print(f"\n--- Measured LiveBrief E2E Latency ---")
    print(f"Moss Retrieval: {response.latency.moss_retrieval_ms:.3f} ms")
    print(f"Evidence Selection: {response.latency.evidence_selection_ms:.3f} ms")
    print(f"Grounded Synthesis: {response.latency.synthesis_ms:.3f} ms")
    print(f"Total Pipeline E2E: {response.latency.total_pipeline_ms:.3f} ms")


def test_e2e_pipeline_absent_evidence_behavior(sample_knowledge_file: Path):
    pipeline = LiveBriefPipeline(index_name="e2e_absent_test")
    pipeline.ingest_and_index_files([sample_knowledge_file])

    # Query with a completely out-of-domain topic with high threshold
    req = QueryRequest(
        query="Explain the migration patterns of arctic blue whales during winter solstice",
        top_k=3,
        min_relevance_threshold=0.98,
    )
    response = pipeline.query(req)

    # Assertions on absent evidence behavior
    assert response.has_sufficient_evidence is False
    assert len(response.key_findings) == 0
    assert len(response.evidence_ledger) == 0
    assert "No relevant knowledge" in response.executive_summary
    assert len(response.caveats_and_gaps) > 0
    # Zero unsupported/hallucinated claims
    assert response.grounding.supported_claims_count == 0
    assert response.grounding.total_claims_count == 0
