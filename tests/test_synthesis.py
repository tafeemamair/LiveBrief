"""Tests for grounded response synthesis and verification."""

import pytest
from livebrief.models.evidence import EvidenceItem, EvidenceSelectionResult, EvidenceSpan
from livebrief.models.response import LatencyBreakdown
from livebrief.synthesis.grounder import GroundedSynthesizer


def test_synthesizer_builds_grounded_response_with_citations():
    synthesizer = GroundedSynthesizer()

    spans = [
        EvidenceSpan(text="LiveBrief uses Moss in-process retrieval for sub-10ms latency.", salience_score=1.5, start_char=0, end_char=62),
    ]
    item = EvidenceItem(
        citation_id=1,
        chunk_id="chk_01",
        doc_id="arch_doc",
        text="LiveBrief uses Moss in-process retrieval for sub-10ms latency.",
        salient_spans=spans,
        relevance_score=0.92,
        final_score=0.92,
        metadata={"source_uri": "docs/arch.md"},
    )

    evidence_result = EvidenceSelectionResult(
        query="What is the latency of LiveBrief retrieval?",
        items=[item],
        total_tokens=20,
        candidate_count=1,
        selected_count=1,
        has_sufficient_evidence=True,
    )

    lat = LatencyBreakdown(moss_retrieval_ms=2.1, total_pipeline_ms=5.4)
    response = synthesizer.synthesize("What is the latency of LiveBrief retrieval?", evidence_result, latency=lat)

    assert response.has_sufficient_evidence is True
    assert len(response.key_findings) > 0
    assert response.key_findings[0].citations == [1]
    assert len(response.evidence_ledger) == 1
    assert response.evidence_ledger[0].citation_id == 1
    assert response.grounding.grounding_score == 1.0
    assert response.grounding.supported_claims_count == len(response.key_findings)
    assert "[1]" in response.executive_summary


def test_synthesizer_handles_absent_evidence_safely():
    synthesizer = GroundedSynthesizer()
    empty_evidence = EvidenceSelectionResult(
        query="Unrelated query about deep sea exploration",
        items=[],
        total_tokens=0,
        candidate_count=0,
        selected_count=0,
        has_sufficient_evidence=False,
    )

    response = synthesizer.synthesize("Unrelated query about deep sea exploration", empty_evidence)

    assert response.has_sufficient_evidence is False
    assert len(response.key_findings) == 0
    assert len(response.evidence_ledger) == 0
    assert "No relevant knowledge" in response.executive_summary
    assert len(response.caveats_and_gaps) > 0
    assert response.grounding.grounding_score == 1.0  # Zero hallucinated unsupported claims
