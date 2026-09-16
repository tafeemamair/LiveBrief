"""Tests for evidence selection, MMR deduplication, and budgeting."""

import pytest
from livebrief.evidence.selector import EvidenceSelector
from livebrief.models.document import Chunk
from livebrief.retrieval.retriever import RetrievalResult, RetrievedCandidate


def test_evidence_selector_deduplicates_redundant_candidates():
    selector = EvidenceSelector(diversity_lambda=0.5)

    c1 = Chunk.create(doc_id="d1", text="LiveBrief provides fast sub-10ms retrieval for AI agents.", chunk_index=0, start_char=0, end_char=50)
    c2 = Chunk.create(doc_id="d2", text="LiveBrief provides fast sub-10ms retrieval for AI agents exactly.", chunk_index=0, start_char=0, end_char=55)
    c3 = Chunk.create(doc_id="d3", text="Hallucination safeguards ensure strict citation grounding.", chunk_index=0, start_char=0, end_char=55)

    candidates = [
        RetrievedCandidate(chunk=c1, score=0.95, rank=1),
        RetrievedCandidate(chunk=c2, score=0.94, rank=2),  # Nearly identical to c1
        RetrievedCandidate(chunk=c3, score=0.80, rank=3),  # Diverse distinct topic
    ]

    retrieval = RetrievalResult(query="retrieval and safeguards", candidates=candidates)
    result = selector.select_evidence(retrieval, max_items=2)

    assert len(result.items) == 2
    selected_doc_ids = [item.doc_id for item in result.items]
    assert "d1" in selected_doc_ids
    # Due to MMR diversity penalty, d3 should be preferred over redundant duplicate d2
    assert "d3" in selected_doc_ids


def test_evidence_selector_token_budget():
    selector = EvidenceSelector()
    c1 = Chunk.create(doc_id="d1", text="A" * 400, chunk_index=0, start_char=0, end_char=400)
    c2 = Chunk.create(doc_id="d2", text="B" * 400, chunk_index=0, start_char=0, end_char=400)

    candidates = [
        RetrievedCandidate(chunk=c1, score=0.9, rank=1),
        RetrievedCandidate(chunk=c2, score=0.8, rank=2),
    ]

    retrieval = RetrievalResult(query="test query", candidates=candidates)
    # Give a tiny token budget (~100 tokens ~ 400 chars)
    result = selector.select_evidence(retrieval, max_tokens=120, max_items=5)

    assert len(result.items) == 1
    assert result.items[0].doc_id == "d1"


def test_evidence_selector_empty_candidates():
    selector = EvidenceSelector()
    retrieval = RetrievalResult(query="empty query", candidates=[])
    result = selector.select_evidence(retrieval)

    assert len(result.items) == 0
    assert result.has_sufficient_evidence is False
