"""Tests for semantic and hybrid retrieval."""

import pytest
from livebrief.models.document import Chunk
from livebrief.models.query import QueryFilter, QueryRequest
from livebrief.moss.indexer import MossIndexer
from livebrief.retrieval.retriever import MossSemanticRetriever


@pytest.fixture
def populated_retriever():
    indexer = MossIndexer(index_name="retrieval_fixture")
    chunks = [
        Chunk.create(
            doc_id="sec_doc",
            text="Security policies require multi-factor authentication across all engineering logins.",
            chunk_index=0,
            start_char=0,
            end_char=80,
            metadata={"domain": "security", "tier": "1"},
        ),
        Chunk.create(
            doc_id="perf_doc",
            text="Performance guidelines dictate sub-10ms response times for in-memory database queries.",
            chunk_index=0,
            start_char=0,
            end_char=85,
            metadata={"domain": "performance", "tier": "1"},
        ),
        Chunk.create(
            doc_id="hr_doc",
            text="Annual performance evaluations occur each calendar year in December.",
            chunk_index=0,
            start_char=0,
            end_char=70,
            metadata={"domain": "hr", "tier": "2"},
        ),
    ]
    indexer.add_chunks(chunks)
    return MossSemanticRetriever(indexer)


def test_retriever_returns_relevant_candidates(populated_retriever):
    request = QueryRequest(query="authentication security policy", top_k=2)
    result = populated_retriever.retrieve(request)

    assert len(result.candidates) > 0
    top_cand = result.candidates[0]
    assert top_cand.chunk.doc_id == "sec_doc"
    assert "authentication" in top_cand.chunk.text
    assert result.latency_ms > 0.0


def test_retriever_metadata_filtering(populated_retriever):
    # Query with filter domain = performance
    req = QueryRequest(
        query="guidelines and policies",
        top_k=5,
        filters=[QueryFilter(field="domain", operator="$eq", value="performance")],
    )
    result = populated_retriever.retrieve(req)

    assert len(result.candidates) == 1
    assert result.candidates[0].chunk.doc_id == "perf_doc"
    assert result.candidates[0].chunk.metadata.get("domain") == "performance"


def test_retriever_empty_query_or_no_match(populated_retriever):
    req = QueryRequest(query="astronomy galaxies astrophysics", min_relevance_threshold=0.99)
    result = populated_retriever.retrieve(req)
    # Strict min threshold filters out low scoring irrelevant hits
    assert len(result.candidates) == 0
