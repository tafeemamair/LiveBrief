"""Structured grounded response and telemetry breakdown models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class KeyFinding(BaseModel):
    """Discrete factual insight directly grounded by citations."""

    claim: str
    citations: List[int] = Field(
        default_factory=list,
        description="Citation indices (e.g. [1], [2]) anchoring this claim.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class EvidenceCitation(BaseModel):
    """Evidence entry in the response ledger."""

    citation_id: int
    doc_id: str
    chunk_id: str
    excerpt: str
    source_uri: Optional[str] = None
    relevance_score: float
    metadata: Dict[str, str] = Field(default_factory=dict)


class GroundingMetric(BaseModel):
    """Evaluation metrics indicating strict factual grounding."""

    grounding_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Fraction of claims and key assertions directly backed by evidence citations.",
    )
    supported_claims_count: int
    total_claims_count: int
    unsupported_claims: List[str] = Field(default_factory=list)


class LatencyBreakdown(BaseModel):
    """Detailed stage-by-stage micro/millisecond execution times."""

    ingestion_ms: float = 0.0
    indexing_ms: float = 0.0
    moss_retrieval_ms: float = 0.0
    evidence_selection_ms: float = 0.0
    synthesis_ms: float = 0.0
    total_pipeline_ms: float = 0.0

    def summary(self) -> Dict[str, str]:
        return {
            "ingestion": f"{self.ingestion_ms:.2f} ms",
            "indexing": f"{self.indexing_ms:.2f} ms",
            "moss_retrieval": f"{self.moss_retrieval_ms:.3f} ms",
            "evidence_selection": f"{self.evidence_selection_ms:.2f} ms",
            "synthesis": f"{self.synthesis_ms:.2f} ms",
            "total_e2e": f"{self.total_pipeline_ms:.2f} ms",
        }


class LiveBriefResponse(BaseModel):
    """Final structured grounded brief returned by Phase 1 pipeline."""

    query: str
    executive_summary: str
    key_findings: List[KeyFinding] = Field(default_factory=list)
    evidence_ledger: List[EvidenceCitation] = Field(default_factory=list)
    grounding: GroundingMetric
    has_sufficient_evidence: bool = True
    caveats_and_gaps: List[str] = Field(default_factory=list)
    latency: LatencyBreakdown
    metadata: Dict[str, Any] = Field(default_factory=dict)
