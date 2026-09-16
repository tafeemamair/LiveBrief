"""Integration tests for Phase 2.3 contextual follow-ups, fresh retrieval, and reliability."""

import json
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path
import pytest
from livebrief.models.query import QueryRequest
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.adapter import VoicePipelineAdapter
from livebrief.voice.context import SessionContextManager
from livebrief.voice.documents import DocumentRegistry
from livebrief.voice.server import create_handler
from livebrief.voice.utterance import UtteranceType


@pytest.fixture
def test_pipeline():
    """Create a pipeline with indexed knowledge for contextual tests."""
    pipeline = LiveBriefPipeline(index_name="test_copilot_pipeline_idx")
    knowledge_path = Path("samples/sample_knowledge.md")
    if knowledge_path.exists():
        pipeline.ingest_and_index_files([knowledge_path])
    return pipeline


@pytest.fixture
def voice_adapter(test_pipeline):
    """Create a VoicePipelineAdapter with an isolated context manager."""
    context_mgr = SessionContextManager(session_id="test_copilot_sess")
    return VoicePipelineAdapter(pipeline=test_pipeline, context_manager=context_mgr)


def test_contextual_followup_fresh_retrieval(voice_adapter):
    """
    Verify that an initial query sets context, and a subsequent follow-up ('Why?')
    resolves context to perform fresh Moss retrieval and evidence verification.
    """
    # 1. Initial query turn
    event1, utype1, trig1, _ = voice_adapter.process_speech_utterance(
        "Can you explain the architecture of LiveBrief?"
    )
    assert trig1 is True
    assert utype1 == UtteranceType.DIRECT_QUERY
    assert event1 is not None
    assert event1.has_sufficient_evidence is True
    assert len(event1.evidence_sources) > 0

    # 2. Contextual follow-up
    event2, utype2, trig2, _ = voice_adapter.process_speech_utterance("What about its latency budget?")
    assert trig2 is True
    assert event2 is not None
    assert event2.contextual_query is not None
    assert "LiveBrief" in event2.contextual_query

    # Verify fresh retrieval returned verified evidence for latency
    assert event2.has_sufficient_evidence is True
    assert event2.grounding_score == 1.0
    assert len(event2.evidence_sources) > 0
    assert any("latency" in src.excerpt.lower() for src in event2.evidence_sources)


def test_contextual_followup_absent_evidence_abstains():
    """
    Verify that when a follow-up query addresses a topic absent from the indexed corpus,
    the pipeline strictly abstains without generating fabricated claims or answering from session memory.
    """
    pipeline_empty = LiveBriefPipeline(index_name="empty_test_copilot_idx")
    context_mgr = SessionContextManager(session_id="absent_test_sess")
    adapter = VoicePipelineAdapter(pipeline=pipeline_empty, context_manager=context_mgr)

    # 1. Simulate initial turn recorded
    context_mgr.add_turn(
        original_query="What is Martian topology?",
        resolved_query="What is Martian topology?",
        summary="Martian topology information.",
    )

    # 2. Follow-up on absent topic
    event2, utype2, trig2, _ = adapter.process_speech_utterance("What about its atmosphere?")
    assert trig2 is True
    assert event2 is not None
    assert event2.has_sufficient_evidence is False
    assert event2.supported_claims_count == 0
    assert event2.total_claims_count == 0
    assert len(event2.key_findings) == 0
    assert len(event2.alerts) > 0
    assert "Insufficient verified evidence" in event2.alerts[0]


def test_context_is_never_injected_as_evidence(voice_adapter):
    """
    Verify that prior turn text/summaries never appear in the evidence ledger.
    Every evidence item must originate from indexed document chunks.
    """
    # Turn 1
    voice_adapter.process_speech_utterance("Can you explain the architecture of LiveBrief?")

    # Turn 2
    event2, _, _, _ = voice_adapter.process_speech_utterance("Why?")
    assert event2 is not None

    for src in event2.evidence_sources:
        # Every citation must reference an indexed chunk and document
        assert src.chunk_id.startswith("sample_knowledge")
        assert src.doc_id == "sample_knowledge"
        assert src.relevance_score > 0.0


def test_session_context_clear_isolation(voice_adapter):
    """Verify that clearing session context wipes history and isolates future queries."""
    voice_adapter.process_speech_utterance("Can you explain the architecture of LiveBrief?")
    assert voice_adapter.context.active_topic is not None

    voice_adapter.context.clear()
    assert voice_adapter.context.active_topic is None
    assert len(voice_adapter.context.history) == 0

    # Next follow-up has no prior anchor
    resolved, anchor = voice_adapter.context.resolve_query("Why?", UtteranceType.FOLLOW_UP)
    assert resolved == "Why?"
    assert anchor is None


@pytest.fixture(scope="module")
def interaction_server():
    web_dir = Path("web")
    server_ready = threading.Event()
    server_holder = {}

    def run_server():
        pipeline = LiveBriefPipeline(index_name="interaction_server_pipeline")
        doc_path = Path("samples/sample_knowledge.md")
        if doc_path.exists():
            pipeline.ingest_and_index_files([doc_path])

        doc_registry = DocumentRegistry(pipeline=pipeline)
        handler = create_handler(web_dir, pipeline=pipeline, document_registry=doc_registry)
        socketserver.TCPServer.allow_reuse_address = True
        server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        server_holder["server"] = server
        server_holder["handler"] = handler
        server_holder["port"] = server.server_address[1]
        server_ready.set()
        try:
            server.serve_forever()
        except Exception:
            pass
        finally:
            if hasattr(pipeline, "indexer") and pipeline.indexer is not None:
                pipeline.indexer._index = None
                pipeline.indexer = None

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server_ready.wait(timeout=5.0)

    port = server_holder["port"]
    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server = server_holder.get("server")
    if server:
        server.shutdown()
        server.server_close()
    handler = server_holder.get("handler")
    if handler:
        handler.pipeline = None
        handler.adapter = None
        handler.document_registry = None
    thread.join(timeout=2.0)


def test_server_malformed_query_returns_http_400(interaction_server):
    """Verify that malformed JSON request bodies to /api/query return HTTP 400."""
    url = f"{interaction_server}/api/query"
    req = urllib.request.Request(
        url,
        data=b"invalid json payload",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == 400


def test_server_rapid_sequential_queries(interaction_server):
    """Verify single-threaded TCPServer stability under rapid sequential requests."""
    url = f"{interaction_server}/api/query"
    session_id = "rapid_seq_test"

    queries = [
        "What are the latency budgets?",
        "How does Moss hybrid retrieval work?",
        "What are the hallucination safeguards?",
        "Can you explain that?",
        "What about token budgeting?",
    ]

    for q in queries:
        payload = json.dumps({"query": q, "session_id": session_id}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["triggered"] is True
            assert data["event"] is not None
            assert data["event"]["session_id"] == session_id
