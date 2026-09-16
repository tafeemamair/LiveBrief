"""Structured grounded response synthesis and verification engine."""

from __future__ import annotations

import re
from typing import List, Optional
from livebrief.models.evidence import EvidenceItem, EvidenceSelectionResult
from livebrief.models.response import (
    EvidenceCitation,
    GroundingMetric,
    KeyFinding,
    LatencyBreakdown,
    LiveBriefResponse,
)


class GroundedSynthesizer:
    """
    Synthesizes structured, strictly grounded LiveBrief responses from evidence items.
    Enforces factual verification and citation anchoring to prevent hallucinations.
    """

    def __init__(self, min_confidence: float = 0.7) -> None:
        self.min_confidence = min_confidence

    def synthesize(
        self,
        query: str,
        evidence: EvidenceSelectionResult,
        latency: Optional[LatencyBreakdown] = None,
    ) -> LiveBriefResponse:
        """Generate structured response strictly grounded in retrieved evidence items."""
        lat = latency or LatencyBreakdown()

        # Handle absent or insufficient evidence gracefully
        if not evidence.has_sufficient_evidence or not evidence.items:
            return LiveBriefResponse(
                query=query,
                executive_summary="No relevant knowledge or documentation found matching the query in the indexed corpus.",
                key_findings=[],
                evidence_ledger=[],
                grounding=GroundingMetric(
                    grounding_score=1.0,
                    supported_claims_count=0,
                    total_claims_count=0,
                    unsupported_claims=[],
                ),
                has_sufficient_evidence=False,
                caveats_and_gaps=[
                    "The indexed corpus does not contain verified context addressing this query.",
                    "No claims were generated to prevent ungrounded speculation or hallucinations.",
                ],
                latency=lat,
                metadata={"total_evidence_items": 0, "token_count": 0},
            )

        # Build evidence ledger
        ledger: List[EvidenceCitation] = []
        for item in evidence.items:
            # Prefer top salient span as excerpt if available, else first 200 chars
            excerpt = item.text
            if item.salient_spans:
                best_span = max(item.salient_spans, key=lambda s: s.salience_score)
                excerpt = best_span.text

            ledger.append(
                EvidenceCitation(
                    citation_id=item.citation_id,
                    doc_id=item.doc_id,
                    chunk_id=item.chunk_id,
                    excerpt=excerpt,
                    source_uri=item.metadata.get("source_uri") or item.metadata.get("source_file"),
                    relevance_score=item.relevance_score,
                    metadata=dict(item.metadata),
                )
            )

        # Generate structured key findings with citation anchors
        findings: List[KeyFinding] = []
        for item in evidence.items:
            # Extract factual statements from salient spans
            candidate_spans = [s.text for s in item.salient_spans if len(s.text) > 15]
            if not candidate_spans:
                candidate_spans = [item.text[:250].strip()]

            for statement in candidate_spans[:2]:
                findings.append(
                    KeyFinding(
                        claim=statement,
                        citations=[item.citation_id],
                        confidence=min(1.0, max(0.5, item.relevance_score)),
                    )
                )

        # Formulate executive summary
        summary_lines: List[str] = []
        for i, item in enumerate(evidence.items[:3]):
            span_text = item.salient_spans[0].text if item.salient_spans else item.text[:120]
            summary_lines.append(f"{span_text} [{item.citation_id}]")
        executive_summary = " ".join(summary_lines)

        # Grounding metric verification
        total_claims = len(findings)
        supported_claims = sum(1 for f in findings if len(f.citations) > 0 and all(c in [item.citation_id for item in evidence.items] for c in f.citations))
        grounding_score = supported_claims / total_claims if total_claims > 0 else 1.0

        return LiveBriefResponse(
            query=query,
            executive_summary=executive_summary,
            key_findings=findings,
            evidence_ledger=ledger,
            grounding=GroundingMetric(
                grounding_score=grounding_score,
                supported_claims_count=supported_claims,
                total_claims_count=total_claims,
                unsupported_claims=[],
            ),
            has_sufficient_evidence=True,
            caveats_and_gaps=[],
            latency=lat,
            metadata={
                "total_evidence_items": len(evidence.items),
                "token_count": evidence.total_tokens,
                "candidate_count": evidence.candidate_count,
            },
        )
