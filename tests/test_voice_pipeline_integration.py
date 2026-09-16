"""Integration tests for Phase 2.2 Voice-to-Intelligence Pipeline."""

from pathlib import Path
import pytest
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.adapter import VoicePipelineAdapter
from livebrief.voice.context import SessionContextManager
from livebrief.voice.utterance import UtteranceType


@pytest.fixture
def voice_adapter() -> VoicePipelineAdapter:
    pipeline = LiveBriefPipeline(index_name="voice_integ_test")
    doc_path = Path("samples/sample_knowledge.md")
    assert doc_path.exists()
    pipeline.ingest_and_index_files([doc_path])
    context_mgr = SessionContextManager(session_id="integration_session")
    return VoicePipelineAdapter(pipeline=pipeline, context_manager=context_mgr)


def test_complete_technical_question_with_sufficient_evidence(voice_adapter: VoicePipelineAdapter):
    utterance = "What are the latency budgets and Moss retrieval mechanisms in LiveBrief?"
    event, utype, triggered, reason = voice_adapter.process_speech_utterance(utterance)

    assert triggered is True
    assert utype == UtteranceType.DIRECT_QUERY
    assert event is not None
    assert event.has_sufficient_evidence is True
    assert len(event.key_findings) > 0
    assert len(event.evidence_sources) > 0
    assert event.grounding_score == 1.0
    assert event.supported_claims_count == len(event.key_findings)
    assert len(event.suggested_followups) > 0
    assert event.e2e_voice_to_ui_ms > 0.0
    assert event.latency.moss_retrieval_ms > 0.0


def test_absent_evidence_query_produces_no_fabricated_claims(voice_adapter: VoicePipelineAdapter):
    # Query completely out of domain with high relevance threshold
    utterance = "Explain the breeding migration of monarch butterflies in winter"
    event, utype, triggered, reason = voice_adapter.process_speech_utterance(utterance)

    assert triggered is True
    assert event is not None
    # For out-of-domain query, verify evidence-first guarantee
    # Note: if threshold permits no chunks or irrelevant chunks, has_sufficient_evidence is false
    # Let's test with strict absence
    pipeline_empty = LiveBriefPipeline(index_name="empty_idx")
    adapter_empty = VoicePipelineAdapter(pipeline=pipeline_empty)
    event_empty, _, triggered_empty, _ = adapter_empty.process_speech_utterance(utterance)

    assert triggered_empty is True
    assert event_empty is not None
    assert event_empty.has_sufficient_evidence is False
    assert len(event_empty.key_findings) == 0
    assert len(event_empty.evidence_sources) == 0
    assert event_empty.supported_claims_count == 0
    assert event_empty.total_claims_count == 0
    assert len(event_empty.alerts) > 0
    assert "Insufficient" in event_empty.alerts[0]


def test_fragmented_speech_is_suppressed(voice_adapter: VoicePipelineAdapter):
    fragments = ["can you", "the test", "and then", "if you"]
    for frag in fragments:
        event, utype, triggered, reason = voice_adapter.process_speech_utterance(frag)
        assert triggered is False
        assert event is None
        assert utype == UtteranceType.FRAGMENT


def test_filler_speech_is_suppressed(voice_adapter: VoicePipelineAdapter):
    fillers = ["um uh yeah", "okay right", "like um"]
    for f in fillers:
        event, utype, triggered, reason = voice_adapter.process_speech_utterance(f)
        assert triggered is False
        assert event is None
        assert utype == UtteranceType.FILLER


def test_short_meaningful_query(voice_adapter: VoicePipelineAdapter):
    utterance = "What about latency?"
    event, utype, triggered, reason = voice_adapter.process_speech_utterance(utterance)

    assert triggered is True
    assert utype == UtteranceType.FOLLOW_UP
    assert event is not None
    assert event.query == "What about latency?"


def test_contextual_followup_resolution(voice_adapter: VoicePipelineAdapter):
    # Turn 1: Main topic
    turn1_text = "What is the LiveBrief system architecture?"
    event1, _, triggered1, _ = voice_adapter.process_speech_utterance(turn1_text)
    assert triggered1 is True
    assert event1 is not None

    # Turn 2: Contextual follow-up
    turn2_text = "What about latency?"
    event2, utype2, triggered2, _ = voice_adapter.process_speech_utterance(turn2_text)
    assert triggered2 is True
    assert utype2 == UtteranceType.FOLLOW_UP
    assert event2 is not None
    assert event2.contextual_query is not None
    assert "LiveBrief system architecture" in event2.contextual_query
    assert event2.has_sufficient_evidence is True


def test_latency_telemetry_fields(voice_adapter: VoicePipelineAdapter):
    utterance = "How does MMR evidence selection work?"
    event, _, triggered, _ = voice_adapter.process_speech_utterance(utterance)

    assert triggered is True
    assert event is not None
    lat = event.latency
    assert lat.moss_retrieval_ms >= 0.0
    assert lat.evidence_selection_ms >= 0.0
    assert lat.synthesis_ms >= 0.0
    assert lat.total_pipeline_ms > 0.0
    assert event.e2e_voice_to_ui_ms > 0.0


def test_repeated_queries_state_isolation(voice_adapter: VoicePipelineAdapter):
    queries = [
        "What are the latency budgets?",
        "What are the hallucination safeguards?",
        "How does Moss retrieval work?",
    ]
    for q in queries:
        event, _, triggered, _ = voice_adapter.process_speech_utterance(q)
        assert triggered is True
        assert event is not None
        assert event.query == q
        assert event.has_sufficient_evidence is True


def test_empty_or_failed_retrieval_safety():
    empty_pipeline = LiveBriefPipeline(index_name="safety_empty_idx")
    adapter = VoicePipelineAdapter(pipeline=empty_pipeline)

    event, utype, triggered, _ = adapter.process_speech_utterance("What is the architecture?")
    assert triggered is True
    assert event is not None
    assert event.has_sufficient_evidence is False
    assert len(event.key_findings) == 0
