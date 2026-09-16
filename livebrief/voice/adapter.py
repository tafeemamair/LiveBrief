"""Integration adapter connecting voice transcript streams to the frozen LiveBriefPipeline."""

from __future__ import annotations

import time
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from livebrief.models.query import QueryRequest
from livebrief.models.response import EvidenceCitation, KeyFinding, LatencyBreakdown, LiveBriefResponse
from livebrief.pipeline import LiveBriefPipeline
from livebrief.voice.context import SessionContextManager
from livebrief.voice.utterance import UtteranceDetector, UtteranceType


class IntelligenceResponseEvent(BaseModel):
    """Structured response contract delivered to the LiveBrief intelligence copilot."""

    session_id: str
    query: str
    contextual_query: Optional[str] = None
    has_sufficient_evidence: bool = True
    suggested_response: str
    key_findings: List[KeyFinding] = Field(default_factory=list)
    evidence_sources: List[EvidenceCitation] = Field(default_factory=list)
    suggested_followups: List[str] = Field(default_factory=list)
    alerts: List[str] = Field(default_factory=list)
    grounding_score: float = 1.0
    supported_claims_count: int = 0
    total_claims_count: int = 0
    latency: LatencyBreakdown
    e2e_voice_to_ui_ms: float = 0.0
    timestamp_ms: float = Field(default_factory=lambda: time.time() * 1000.0)


def generate_suggested_followups(response: LiveBriefResponse) -> List[str]:
    """Generate contextual follow-up query suggestions based on retrieved findings."""
    if not response.has_sufficient_evidence or not response.key_findings:
        return [
            "What topics are indexed in the knowledge base?",
            "Can you explain the LiveBrief architecture?",
        ]

    suggestions: List[str] = []
    text_corpus = " ".join(f.claim for f in response.key_findings).lower()

    if "latency" in text_corpus or "moss" in text_corpus:
        suggestions.append("How does Moss achieve sub-10ms retrieval?")
    if "hallucination" in text_corpus or "grounding" in text_corpus:
        suggestions.append("What are the three hallucination safeguards?")
    if "mmr" in text_corpus or "evidence" in text_corpus:
        suggestions.append("How does MMR evidence selection work?")
    if "hybrid" in text_corpus or "alpha" in text_corpus:
        suggestions.append("What is the hybrid alpha weighting formula?")

    if not suggestions:
        suggestions = [
            "Can you elaborate on these findings?",
            "What are the implementation details?",
        ]

    return suggestions[:3]


class VoicePipelineAdapter:
    """
    Adapter bridging Phase 2.1 speech transcripts into the frozen Phase 1 LiveBriefPipeline.
    Preserves strict Phase 1 retrieval architecture and evidence-first guarantees.
    """

    def __init__(
        self,
        pipeline: LiveBriefPipeline,
        context_manager: Optional[SessionContextManager] = None,
    ) -> None:
        self.pipeline = pipeline
        self.context = context_manager or SessionContextManager()

    def process_speech_utterance(
        self,
        text: str,
        session_id: Optional[str] = None,
    ) -> Tuple[Optional[IntelligenceResponseEvent], UtteranceType, bool, str]:
        """
        Process a speech utterance:
        1. Classify with UtteranceDetector.
        2. If non-substantive (filler/fragment), suppress retrieval.
        3. If follow-up, resolve context via SessionContextManager.
        4. Invoke frozen LiveBriefPipeline.query().
        5. Return structured IntelligenceResponseEvent.
        """
        t0 = time.perf_counter()
        active_session = session_id or self.context.session_id

        # 1. Utterance Classification Gate
        utterance_type, should_trigger, reason = UtteranceDetector.classify(text)
        if not should_trigger:
            return None, utterance_type, False, reason

        # 2. Context Resolution (for follow-ups)
        query_to_run, context_anchor = self.context.resolve_query(text, utterance_type)

        # 3. Invoke Frozen Phase 1 Pipeline
        req = QueryRequest(query=query_to_run, top_k=5, alpha=0.8)
        pipeline_resp = self.pipeline.query(req)

        # 4. Generate Follow-up Chips and Alerts
        followups = generate_suggested_followups(pipeline_resp)
        alerts: List[str] = []
        if not pipeline_resp.has_sufficient_evidence:
            alerts.append("Insufficient verified evidence found in knowledge base. No speculative claims were generated.")

        total_e2e_ms = (time.perf_counter() - t0) * 1000.0

        # 5. Build Typed Response Event
        event = IntelligenceResponseEvent(
            session_id=active_session,
            query=text,
            contextual_query=query_to_run if context_anchor else None,
            has_sufficient_evidence=pipeline_resp.has_sufficient_evidence,
            suggested_response=pipeline_resp.executive_summary,
            key_findings=pipeline_resp.key_findings,
            evidence_sources=pipeline_resp.evidence_ledger,
            suggested_followups=followups,
            alerts=alerts,
            grounding_score=pipeline_resp.grounding.grounding_score,
            supported_claims_count=pipeline_resp.grounding.supported_claims_count,
            total_claims_count=pipeline_resp.grounding.total_claims_count,
            latency=pipeline_resp.latency,
            e2e_voice_to_ui_ms=total_e2e_ms,
        )

        # 6. Update Session Context (if evidence was sufficient)
        if pipeline_resp.has_sufficient_evidence:
            self.context.add_turn(
                original_query=text,
                resolved_query=query_to_run,
                summary=pipeline_resp.executive_summary,
            )

        return event, utterance_type, True, reason
